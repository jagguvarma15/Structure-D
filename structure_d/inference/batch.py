"""Batch processing: group chunks and dispatch to the configured provider."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Type

import structlog
from pydantic import BaseModel

from structure_d.config import get_settings
from structure_d.exceptions import InferenceError
from structure_d.inference.providers import BaseLLMProvider, VLLMProvider
from structure_d.inference.structured_output import StructuredOutputBuilder
from structure_d.schemas.base import ExtractionResult, TaskType, TextChunk

logger = structlog.get_logger(__name__)


class BatchProcessor:
    """
    Process a list of text chunks through an LLM provider in configurable batches.

    Accepts any :class:`~structure_d.inference.providers.BaseLLMProvider`
    implementation – vLLM, OpenAI, Anthropic, Gemini, or Ollama.  When no
    provider is supplied the default is :class:`VLLMProvider`.

    Requests within each batch run concurrently via ``asyncio.gather``.

    Usage::

        processor = BatchProcessor(schema_cls=InvoiceSchema, provider=OpenAIProvider())
        results = await processor.process(chunks, model="gpt-4o")
    """

    def __init__(
        self,
        schema_cls: Type[BaseModel],
        task: TaskType = TaskType.EXTRACTION,
        provider: BaseLLMProvider | None = None,
        max_batch_size: int | None = None,
        few_shot_examples: list[dict[str, str]] | None = None,
    ) -> None:
        settings = get_settings()
        self.provider = provider or VLLMProvider()
        self.schema_cls = schema_cls
        self.task = task
        self.max_batch_size = max_batch_size or settings.inference.batch.max_batch_size
        self.builder = StructuredOutputBuilder(
            schema_cls=schema_cls,
            task=task,
            few_shot_examples=few_shot_examples,
        )

    async def process(
        self,
        chunks: list[TextChunk],
        model: str | None = None,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> list[ExtractionResult]:
        """
        Send all *chunks* through the provider and return :class:`ExtractionResult` objects.

        Parameters
        ----------
        chunks:
            Text chunks to process.
        model:
            Override the model for this batch (passed to the provider;
            providers that don't support runtime model switching ignore it).
        temperature:
            Sampling temperature.
        max_tokens:
            Maximum tokens to generate per chunk.
        """
        results: list[ExtractionResult] = []

        for i in range(0, len(chunks), self.max_batch_size):
            batch = chunks[i : i + self.max_batch_size]
            batch_results = await asyncio.gather(
                *(
                    self._process_one(chunk, model, temperature, max_tokens)
                    for chunk in batch
                ),
                return_exceptions=True,
            )
            for chunk, res in zip(batch, batch_results):
                if isinstance(res, Exception):
                    logger.error(
                        "batch_item_error",
                        chunk_id=chunk.metadata.chunk_id,
                        error=str(res),
                    )
                    results.append(
                        ExtractionResult(
                            document_id=chunk.metadata.document_id,
                            chunk_id=chunk.metadata.chunk_id,
                            task=self.task,
                            model_used=model or "",
                            is_valid=False,
                            validation_errors=[str(res)],
                        )
                    )
                else:
                    results.append(res)

        return results

    async def _process_one(
        self,
        chunk: TextChunk,
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> ExtractionResult:
        system_prompt = self.builder.build_system_prompt()

        t0 = time.monotonic()
        try:
            pr = await self.provider.generate(
                prompt=chunk.text,
                schema=self.schema_cls,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )
        except InferenceError as exc:
            latency = (time.monotonic() - t0) * 1000
            return ExtractionResult(
                document_id=chunk.metadata.document_id,
                chunk_id=chunk.metadata.chunk_id,
                task=self.task,
                model_used=model or "",
                raw_output="",
                is_valid=False,
                validation_errors=[str(exc)],
                latency_ms=round(latency, 1),
            )

        latency = (time.monotonic() - t0) * 1000
        structured = pr.output.model_dump()
        # Ensure raw_text is valid JSON even if the provider returned something else
        raw_text = pr.raw_text or json.dumps(structured)

        return ExtractionResult(
            document_id=chunk.metadata.document_id,
            chunk_id=chunk.metadata.chunk_id,
            task=self.task,
            model_used=pr.model_used,
            raw_output=raw_text,
            structured_output=structured,
            is_valid=True,
            latency_ms=round(latency, 1),
            token_usage=pr.token_usage,
        )
