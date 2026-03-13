"""Tests for RetryHandler: validation retry logic with mock providers."""

from __future__ import annotations

import json
from typing import Any, Type

from pydantic import BaseModel

from structure_d.exceptions import InferenceError
from structure_d.inference.providers import BaseLLMProvider, ProviderResult
from structure_d.schemas.base import DocumentFormat, ExtractionResult, TaskType
from structure_d.schemas.generic import KeyValueExtraction, KeyValuePair
from structure_d.validation.retry import RetryHandler
from tests.conftest import FakeProvider


# ── Helpers ──────────────────────────────────────────────────────────────────


class _FixOnRetryProvider(BaseLLMProvider):
    """Fails on first call, succeeds on second."""

    def __init__(self) -> None:
        self._calls = 0

    async def generate(self, prompt: str, schema: Type[BaseModel], **kw: Any) -> ProviderResult:
        self._calls += 1
        if self._calls == 1:
            raise InferenceError("first attempt fails")
        kv = KeyValueExtraction(pairs=[KeyValuePair(key="k", value="v")])
        return ProviderResult(
            output=kv,
            raw_text=json.dumps(kv.model_dump()),
            model_used="retry-model",
        )

    async def generate_text(self, prompt: str, **kw: Any) -> str:
        return ""


class _AlwaysFailProvider(BaseLLMProvider):
    """Always raises InferenceError."""

    async def generate(self, prompt: str, schema: Type[BaseModel], **kw: Any) -> ProviderResult:
        raise InferenceError("permanent failure")

    async def generate_text(self, prompt: str, **kw: Any) -> str:
        raise InferenceError("permanent failure")


def _invalid_result() -> ExtractionResult:
    return ExtractionResult(
        document_id="doc-1",
        chunk_id="chunk-1",
        task=TaskType.EXTRACTION,
        is_valid=False,
        validation_errors=["output was empty"],
    )


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_already_valid_skips_retry():
    """If the result is already valid, RetryHandler should return it immediately."""
    handler = RetryHandler(
        schema_cls=KeyValueExtraction, provider=FakeProvider(), max_retries=3,
    )
    result = ExtractionResult(
        document_id="d", chunk_id="c", is_valid=True,
        structured_output={"pairs": []},
    )
    out = await handler.validate_and_retry(result, original_text="text")
    assert out.is_valid is True
    assert out is result


async def test_retry_succeeds_on_second_attempt():
    """RetryHandler should recover when the provider succeeds on retry."""
    handler = RetryHandler(
        schema_cls=KeyValueExtraction,
        provider=_FixOnRetryProvider(),
        max_retries=3,
    )
    result = _invalid_result()
    out = await handler.validate_and_retry(result, original_text="some text")

    assert out.is_valid is True
    assert out.model_used == "retry-model"
    assert out.validation_errors == []


async def test_retry_exhausted_stays_invalid():
    """When all retries fail, the result should remain invalid with errors."""
    handler = RetryHandler(
        schema_cls=KeyValueExtraction,
        provider=_AlwaysFailProvider(),
        max_retries=2,
    )
    result = _invalid_result()
    out = await handler.validate_and_retry(result, original_text="text")

    assert out.is_valid is False
    assert len(out.validation_errors) >= 1
    assert "permanent failure" in out.validation_errors[0]


async def test_retry_disabled_via_config(monkeypatch):
    """When retry_with_refined_prompt is False, no retries should happen."""
    handler = RetryHandler(
        schema_cls=KeyValueExtraction,
        provider=_AlwaysFailProvider(),
        max_retries=5,
    )
    handler.retry_with_prompt = False

    result = _invalid_result()
    out = await handler.validate_and_retry(result, original_text="text")

    assert out.is_valid is False
    assert out.validation_errors == ["output was empty"]
