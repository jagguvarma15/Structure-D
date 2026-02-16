"""
Main pipeline orchestrator.

Wires together ingestion → preprocessing → routing → inference →
validation → storage into a single async call.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Type

import structlog
from pydantic import BaseModel

from structure_d.config import get_settings, load_settings
from structure_d.inference.batch import BatchProcessor
from structure_d.inference.vllm_client import VLLMClient
from structure_d.ingestion.manager import IngestionManager
from structure_d.models.registry import ModelRegistry
from structure_d.models.router import ModelRouter
from structure_d.preprocessing.chunker import Chunker
from structure_d.preprocessing.normalizer import normalize_text
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

    # ── Public API ────────────────────────────────────────────────────────────

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

        # 1. Ingest
        logger.info("pipeline_start", file=str(file_path), format=file_path.suffix)
        doc = await self.ingestion.ingest(file_path, parser_name=parser_name)
        source_format = doc.metadata.format

        # 2. Pre-process
        text = normalize_text(
            doc.text,
            normalize_unicode=settings.preprocessing.normalize_unicode,
            strip_boilerplate=settings.preprocessing.strip_boilerplate,
        )
        chunks = self.chunker.chunk(text, document_id=doc.metadata.document_id)

        # Propagate format to chunk metadata
        for chunk in chunks:
            chunk.metadata.source_format = source_format

        logger.info("pipeline_chunked", chunks=len(chunks), format=source_format.value)

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
            result = await self.retry_handler.validate_and_retry(
                result, original_text=chunk.text, model=model
            )
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
