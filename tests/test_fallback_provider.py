"""Tests for FallbackProvider and resolve_provider."""

from __future__ import annotations

import json
from typing import Any, Type

import pytest
from pydantic import BaseModel

from structure_d.config import Settings, load_settings
from structure_d.exceptions import InferenceError
from structure_d.inference.providers import (
    FallbackProvider,
    ProviderResult,
    BaseLLMProvider,
    resolve_provider,
)
from structure_d.schemas.generic import KeyValueExtraction, KeyValuePair
from tests.conftest import FakeProvider


# ── Helpers ──────────────────────────────────────────────────────────────────


class _FailProvider(BaseLLMProvider):
    """Always raises InferenceError (simulates vLLM being unreachable)."""

    async def generate(self, prompt: str, schema: Type[BaseModel], **kw: Any) -> ProviderResult:
        raise InferenceError("connection refused", model="vllm", status_code=503)

    async def generate_text(self, prompt: str, **kw: Any) -> str:
        raise InferenceError("connection refused")


class _CountingProvider(BaseLLMProvider):
    """Records how many times it was called."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, prompt: str, schema: Type[BaseModel], **kw: Any) -> ProviderResult:
        self.calls += 1
        kv = KeyValueExtraction(pairs=[KeyValuePair(key="k", value="v")])
        return ProviderResult(
            output=kv,
            raw_text=json.dumps(kv.model_dump()),
            model_used="counting-model",
        )

    async def generate_text(self, prompt: str, **kw: Any) -> str:
        self.calls += 1
        return "text"


# ── FallbackProvider unit tests ───────────────────────────────────────────────


async def test_fallback_not_triggered_when_primary_succeeds():
    """When primary succeeds, fallback should never be called."""
    fallback = _CountingProvider()
    provider = FallbackProvider(primary=FakeProvider(), fallback=fallback)

    result = await provider.generate(
        prompt="extract", schema=KeyValueExtraction,
    )
    assert result.model_used == "fake-model"
    assert fallback.calls == 0  # fallback untouched


async def test_fallback_called_when_primary_fails():
    """When primary raises InferenceError, fallback should be used."""
    fallback = _CountingProvider()
    provider = FallbackProvider(primary=_FailProvider(), fallback=fallback)

    result = await provider.generate(
        prompt="extract", schema=KeyValueExtraction,
    )
    assert result.model_used == "counting-model"
    assert fallback.calls == 1


async def test_fallback_generate_text_on_primary_failure():
    """generate_text should also fall back on InferenceError."""
    fallback = _CountingProvider()
    provider = FallbackProvider(primary=_FailProvider(), fallback=fallback)

    text = await provider.generate_text(prompt="summarise")
    assert text == "text"
    assert fallback.calls == 1


async def test_fallback_propagates_fallback_error():
    """If both primary and fallback fail, the fallback's error should propagate."""
    provider = FallbackProvider(primary=_FailProvider(), fallback=_FailProvider())

    with pytest.raises(InferenceError):
        await provider.generate(prompt="extract", schema=KeyValueExtraction)


async def test_generate_text_primary_success():
    """generate_text uses primary when it succeeds, fallback stays silent."""
    fallback = _CountingProvider()
    provider = FallbackProvider(primary=FakeProvider(), fallback=fallback)

    text = await provider.generate_text(prompt="hello")
    assert fallback.calls == 0


# ── resolve_provider tests ────────────────────────────────────────────────────


def test_resolve_provider_no_fallback(tmp_path):
    """With no fallback_provider configured, resolve_provider returns a plain provider."""
    cfg = tmp_path / "test.yaml"
    cfg.write_text(
        "inference:\n"
        "  provider:\n"
        "    provider: 'ollama'\n"
        "    fallback_provider: null\n"
        "    ollama:\n"
        "      base_url: 'http://localhost:11434'\n"
        "      model: 'llama3.1:8b'\n"
    )
    settings = load_settings(cfg)
    provider = resolve_provider(settings)
    # Should be a plain OllamaProvider, not wrapped in FallbackProvider
    assert not isinstance(provider, FallbackProvider)
    assert type(provider).__name__ == "OllamaProvider"


def test_resolve_provider_with_fallback(tmp_path):
    """With fallback_provider set, resolve_provider returns a FallbackProvider."""
    cfg = tmp_path / "test.yaml"
    cfg.write_text(
        "inference:\n"
        "  provider:\n"
        "    provider: 'vllm'\n"
        "    fallback_provider: 'anthropic'\n"
        "    anthropic:\n"
        "      model: 'claude-3-5-sonnet-20241022'\n"
        "      api_key: 'sk-test'\n"
    )
    settings = load_settings(cfg)
    provider = resolve_provider(settings)

    assert isinstance(provider, FallbackProvider)
    assert type(provider.primary).__name__ == "VLLMProvider"
    assert type(provider.fallback).__name__ == "AnthropicProvider"


def test_provider_config_fallback_field_defaults_null():
    """fallback_provider should default to None when not set."""
    settings = Settings()
    assert settings.inference.provider.fallback_provider is None
