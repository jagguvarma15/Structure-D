"""Tests for BatchProcessor: batching, error handling, concurrency."""

from __future__ import annotations

import json
from typing import Any, Type

import pytest
from pydantic import BaseModel

from structure_d.exceptions import InferenceError
from structure_d.inference.batch import BatchProcessor
from structure_d.inference.providers import BaseLLMProvider, ProviderResult
from structure_d.schemas.base import ChunkMetadata, DocumentFormat, TaskType, TextChunk
from structure_d.schemas.generic import KeyValueExtraction, KeyValuePair
from tests.conftest import FakeProvider


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunks(n: int) -> list[TextChunk]:
    return [
        TextChunk(
            text=f"chunk text {i}",
            metadata=ChunkMetadata(
                chunk_id=f"c-{i}",
                document_id="doc-1",
                source_format=DocumentFormat.PLAIN_TEXT,
                token_count=5,
            ),
        )
        for i in range(n)
    ]


class _FailingProvider(BaseLLMProvider):
    """Provider that always raises InferenceError."""

    async def generate(self, prompt: str, schema: Type[BaseModel], **kw: Any) -> ProviderResult:
        raise InferenceError("boom", model="fail-model", status_code=500)

    async def generate_text(self, prompt: str, **kw: Any) -> str:
        raise InferenceError("boom")


class _AlternatingProvider(BaseLLMProvider):
    """Succeeds on even indices, fails on odd indices."""

    def __init__(self) -> None:
        self._call_count = 0

    async def generate(self, prompt: str, schema: Type[BaseModel], **kw: Any) -> ProviderResult:
        idx = self._call_count
        self._call_count += 1
        if idx % 2 != 0:
            raise InferenceError("odd failure")
        kv = KeyValueExtraction(pairs=[KeyValuePair(key="k", value=f"v{idx}")])
        return ProviderResult(
            output=kv,
            raw_text=json.dumps(kv.model_dump()),
            model_used="alt-model",
            token_usage={"prompt_tokens": 5, "completion_tokens": 5},
        )

    async def generate_text(self, prompt: str, **kw: Any) -> str:
        return ""


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_process_single_chunk():
    """Processing one chunk should return one valid ExtractionResult."""
    bp = BatchProcessor(schema_cls=KeyValueExtraction, provider=FakeProvider())
    results = await bp.process(_make_chunks(1))

    assert len(results) == 1
    assert results[0].is_valid is True
    assert results[0].chunk_id == "c-0"


async def test_process_multiple_batches():
    """Chunks exceeding max_batch_size should be split across batches."""
    bp = BatchProcessor(
        schema_cls=KeyValueExtraction,
        provider=FakeProvider(),
        max_batch_size=2,
    )
    results = await bp.process(_make_chunks(5))

    assert len(results) == 5
    assert all(r.is_valid for r in results)


async def test_process_handles_provider_error():
    """A provider failure should produce an invalid result, not crash."""
    bp = BatchProcessor(schema_cls=KeyValueExtraction, provider=_FailingProvider())
    results = await bp.process(_make_chunks(2))

    assert len(results) == 2
    for r in results:
        assert r.is_valid is False
        assert len(r.validation_errors) >= 1


async def test_process_partial_failure():
    """Mixed success/failure should return results for every chunk."""
    bp = BatchProcessor(
        schema_cls=KeyValueExtraction,
        provider=_AlternatingProvider(),
        max_batch_size=10,
    )
    results = await bp.process(_make_chunks(4))

    assert len(results) == 4
    valid = [r for r in results if r.is_valid]
    invalid = [r for r in results if not r.is_valid]
    assert len(valid) >= 1
    assert len(invalid) >= 1


async def test_process_empty_input():
    """An empty chunk list should return an empty result list."""
    bp = BatchProcessor(schema_cls=KeyValueExtraction, provider=FakeProvider())
    results = await bp.process([])
    assert results == []
