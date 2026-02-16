"""Batch processing: group chunks and dispatch to vLLM efficiently."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Type

import structlog
from pydantic import BaseModel

from structure_d.config import get_settings
from structure_d.inference.structured_output import StructuredOutputBuilder
from structure_d.inference.vllm_client import VLLMClient
from structure_d.schemas.base import ExtractionResult, TaskType, TextChunk

logger = structlog.get_logger(__name__)


class BatchProcessor:
    """
    Process a list of text chunks through vLLM in configurable batches.

    Usage::

        processor = BatchProcessor(schema_cls=InvoiceSchema)
        results = await processor.process(chunks, model="llama-3.1-8b")
    """

    def __init__(
        self,
        schema_cls: Type[BaseModel],
        task: TaskType = TaskType.EXTRACTION,
        client: VLLMClient | None = None,
        max_batch_size: int | None = None,
        few_shot_examples: list[dict[str, str]] | None = None,
    ) -> None:
        settings = get_settings()
        self.client = client or VLLMClient()
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
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> list[ExtractionResult]:
        """
        Send all *chunks* through vLLM and return :class:`ExtractionResult` objects.

        Requests within each batch run concurrently via ``asyncio.gather``.
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
                            model_used=model,
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
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> ExtractionResult:
        messages = self.builder.build_messages(chunk.text)
        schema = self.builder.json_schema()

        t0 = time.monotonic()
        response = await self.client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=schema,
        )
        latency = (time.monotonic() - t0) * 1000

        # Parse response
        raw_text = ""
        usage: dict[str, int] = {}
        choices = response.get("choices", [])
        if choices:
            raw_text = choices[0].get("message", {}).get("content", "")
        if "usage" in response:
            usage = {
                "prompt_tokens": response["usage"].get("prompt_tokens", 0),
                "completion_tokens": response["usage"].get("completion_tokens", 0),
                "total_tokens": response["usage"].get("total_tokens", 0),
            }

        return ExtractionResult(
            document_id=chunk.metadata.document_id,
            chunk_id=chunk.metadata.chunk_id,
            task=self.task,
            model_used=model,
            raw_output=raw_text,
            latency_ms=round(latency, 1),
            token_usage=usage,
        )
