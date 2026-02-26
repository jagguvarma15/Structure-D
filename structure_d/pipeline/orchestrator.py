"""
Main pipeline orchestrator.

Wires together ingestion → preprocessing → routing → inference →
validation → storage into a single async call.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal, Type

import structlog
from pydantic import BaseModel

from structure_d.config import get_settings, load_settings
from structure_d.inference.batch import BatchProcessor
from structure_d.inference.vllm_client import VLLMClient
from structure_d.ingestion.manager import IngestionManager
from structure_d.models.registry import ModelRegistry
from structure_d.models.router import ModelRouter
from structure_d.monitoring.metrics import MetricsCollector
from structure_d.preprocessing.chunker import Chunker
from structure_d.preprocessing.normalizer import normalize_text
from structure_d.retrieval.embeddings import EmbeddingService
from structure_d.retrieval.rag_pipeline import RAGPipeline
from structure_d.retrieval.vector_store import VectorStoreBase
from structure_d.schemas.base import (
    DocumentFormat,
    ExtractionResult,
    ParsedDocument,
    TaskType,
    TextChunk,
)
from structure_d.storage.csv_store import CSVWriter
from structure_d.storage.jsonl import JSONLWriter
from structure_d.validation.retry import RetryHandler

logger = structlog.get_logger(__name__)


class Pipeline:
    """
    High-level async pipeline: file → structured data.

    Works with **any** supported file format (PDF, image, HTML, DOCX, XLSX,
    PPTX, email, audio transcript, plain text, CSV, Markdown).  The schema
    is provided at construction time and determines what gets extracted.

    Usage::

        from structure_d.pipeline import Pipeline
        from structure_d.schemas.generic import KeyValueExtraction

        pipeline = Pipeline(schema_cls=KeyValueExtraction)
        results = await pipeline.run(Path("docs/report.pdf"))

    Each call to :meth:`run` performs:

    1. **Ingest** – parse the file via the appropriate format parser.
    2. **Pre-process** – normalise and chunk the text.
    3. **Route** – select the best model for the task.
    4. **Infer** – send chunks to vLLM in batches.
    5. **Validate** – check outputs against the Pydantic schema; retry on error.
    6. **Store** – write results to JSONL / CSV / database.
    """

    def __init__(
        self,
        schema_cls: Type[BaseModel],
        task: TaskType = TaskType.EXTRACTION,
        config_path: str | Path | None = None,
        *,
        # Optional component overrides
        ingestion_manager: IngestionManager | None = None,
        model_registry: ModelRegistry | None = None,
        vllm_client: VLLMClient | None = None,
        vector_store: VectorStoreBase | None = None,
        enable_rag: bool | None = None,
    ) -> None:
        # Load settings
        if config_path:
            settings = load_settings(config_path)
            import structure_d.config as _cfg

            _cfg._settings = settings
        settings = get_settings()

        self.schema_cls = schema_cls
        self.task = task

        # Components
        self.ingestion = ingestion_manager or IngestionManager()
        self.chunker = Chunker(
            strategy=settings.preprocessing.chunking.strategy,
            max_tokens=settings.preprocessing.chunking.max_tokens,
            overlap_tokens=settings.preprocessing.chunking.overlap_tokens,
            heading_level=settings.preprocessing.chunking.heading_level,
        )

        registry_path = settings.models.registry_path
        self.registry = model_registry or ModelRegistry.from_yaml(registry_path)
        self.router = ModelRouter(self.registry)

        self.client = vllm_client or VLLMClient()
        self.batch_processor = BatchProcessor(
            schema_cls=schema_cls,
            task=task,
            client=self.client,
        )
        self.retry_handler = RetryHandler(
            schema_cls=schema_cls,
            task=task,
            client=self.client,
        )

        self.jsonl_writer = JSONLWriter()
        self.csv_writer = CSVWriter()
        
        # Metrics collector
        self.metrics = MetricsCollector()
        if settings.monitoring.prometheus.enabled:
            self.metrics.start_server(settings.monitoring.prometheus.port)
        
        # RAG pipeline (optional)
        self.enable_rag = enable_rag if enable_rag is not None else settings.retrieval.enabled
        self.rag_pipeline: RAGPipeline | None = None
        if self.enable_rag and vector_store:
            embedding_service = EmbeddingService()
            self.rag_pipeline = RAGPipeline(
                vector_store=vector_store,
                embedding_service=embedding_service,
                client=self.client,
            )

        # Index (built on demand via build_index)
        self._vector_store = vector_store
        self._embedding_service = EmbeddingService() if (vector_store or enable_rag) else None

    # ── Public API ────────────────────────────────────────────────────────────

    async def build_index(
        self,
        file_path: Path,
        index_type: Literal["vector", "summary"] = "vector",
        *,
        vector_store: VectorStoreBase | None = None,
        parser_name: str | None = None,
    ) -> Any:
        """
        Load file, chunk into nodes, and build an index.

        Returns a :class:`VectorStoreIndex` or :class:`SummaryIndex` with nodes
        inserted. Use :meth:`index.as_query_engine(llm_client=self.client)` for RAG.

        Parameters
        ----------
        file_path
            Path to the file to index.
        index_type
            ``"vector"`` (embed + vector store) or ``"summary"`` (in-memory list).
        vector_store
            Required for ``index_type="vector"`` unless the pipeline was created
            with a vector_store (e.g. RAG enabled).
        parser_name
            Override parser (default: auto-detect from extension).
        """
        from structure_d.indexing import DocumentReader, SummaryIndex, VectorStoreIndex

        reader = DocumentReader(ingestion_manager=self.ingestion, chunker=self.chunker)
        nodes = await reader.load_and_chunk(file_path, parser_name=parser_name)
        if not nodes:
            logger.warning("build_index_no_nodes", path=str(file_path))
        if index_type == "summary":
            index = SummaryIndex(nodes=nodes)
            return index
        store = vector_store or self._vector_store
        if store is None:
            raise ValueError(
                "vector_store is required for index_type='vector'. "
                "Pass vector_store to Pipeline() or to build_index()."
            )
        emb = self._embedding_service or EmbeddingService()
        index = VectorStoreIndex(vector_store=store, embedding_service=emb)
        await index.insert_nodes(nodes)
        return index

    async def run(
        self,
        file_path: Path,
        *,
        parser_name: str | None = None,
        model: str | None = None,
        save_format: str | None = None,
        output_filename: str | None = None,
    ) -> list[ExtractionResult]:
        """
        Run the full pipeline on a single file.

        Parameters
        ----------
        file_path:
            Path to the file to process (any supported format).
        parser_name:
            Override the parser (default: auto-detect from extension).
        model:
            Override the model (default: auto-route by task).
        save_format:
            "jsonl", "csv" or None (return results without saving).
        output_filename:
            Custom filename for the output file.
        """
        t0 = time.monotonic()
        settings = get_settings()

        # Track active request
        with self.metrics.track_request():
            # 1. Ingest
            logger.info("pipeline_start", file=str(file_path), format=file_path.suffix)
            ingest_start = time.monotonic()
            doc: ParsedDocument = await self.ingestion.ingest(file_path, parser_name=parser_name)
            ingest_elapsed = (time.monotonic() - ingest_start) * 1000
            self.metrics.record_ingestion(1)
            logger.debug("ingestion_complete", elapsed_ms=round(ingest_elapsed, 1))
            source_format = doc.metadata.format

        # 2. Pre-process
        text = normalize_text(
            doc.text,
            normalize_unicode=settings.preprocessing.normalize_unicode,
            strip_boilerplate=settings.preprocessing.strip_boilerplate,
        )
        chunks: list[TextChunk] = self.chunker.chunk(text, document_id=doc.metadata.document_id)

        # Propagate format to chunk metadata
        for chunk in chunks:
            chunk.metadata.source_format = source_format

        logger.info("pipeline_chunked", chunks=len(chunks), format=source_format.value)
        self.metrics.record_chunks(len(chunks))
        
        # 2.5. Index chunks for RAG (if enabled)
        if self.rag_pipeline:
            try:
                await self.rag_pipeline.index_chunks(chunks)
                logger.info("rag_indexed", chunks=len(chunks))
            except Exception as e:
                logger.warning("rag_indexing_failed", error=str(e))

        # 3. Route
        if model is None:
            avg_tokens = sum(c.metadata.token_count for c in chunks) // max(len(chunks), 1)
            # Use multimodal model for image-based formats
            prefer_mm = source_format in (DocumentFormat.IMAGE,)
            entry = self.router.route(
                self.task,
                input_tokens=avg_tokens,
                prefer_multimodal=prefer_mm,
            )
            model = entry.name

        # 4. Infer
        results = await self.batch_processor.process(chunks, model=model)

        # 5. Validate + retry
        validated: list[ExtractionResult] = []
        for result, chunk in zip(results, chunks):
            result.source_format = source_format
            validate_start = time.monotonic()
            result = await self.retry_handler.validate_and_retry(
                result, original_text=chunk.text, model=model
            )
            validate_elapsed = (time.monotonic() - validate_start) * 1000
            if not result.is_valid:
                self.metrics.record_validation_failure(1)
                logger.debug("validation_failed", elapsed_ms=round(validate_elapsed, 1))
            
            # Record token usage
            if result.token_usage:
                prompt_tokens = result.token_usage.get("prompt_tokens", 0)
                completion_tokens = result.token_usage.get("completion_tokens", 0)
                self.metrics.record_tokens(prompt=prompt_tokens, completion=completion_tokens)
            
            # Record inference latency
            if result.latency_ms:
                self.metrics.record_inference_latency(result.latency_ms / 1000.0)
            
            validated.append(result)

        # 6. Store
        fmt = save_format or settings.storage.default_format
        fname = output_filename or f"{file_path.stem}_output"
        if fmt == "jsonl":
            self.jsonl_writer.write(validated, f"{fname}.jsonl")
        elif fmt == "csv":
            self.csv_writer.write(validated, f"{fname}.csv")

        elapsed = (time.monotonic() - t0) * 1000
        valid_count = sum(1 for r in validated if r.is_valid)
        
        # Record overall pipeline latency
        self.metrics.record_inference_latency(elapsed / 1000.0)
        
        logger.info(
            "pipeline_complete",
            file=str(file_path),
            format=source_format.value,
            chunks=len(chunks),
            results=len(validated),
            valid=valid_count,
            elapsed_ms=round(elapsed, 1),
        )

        return validated

    async def run_many(
        self,
        file_paths: list[Path],
        **kwargs: Any,
    ) -> dict[str, list[ExtractionResult]]:
        """Run the pipeline on multiple files (any format) and return results keyed by filename."""
        all_results: dict[str, list[ExtractionResult]] = {}
        for fp in file_paths:
            results = await self.run(fp, **kwargs)
            all_results[fp.name] = results
        return all_results
