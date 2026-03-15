"""Multi-LLM provider support: OpenAI, Anthropic, Gemini, Ollama, vLLM."""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Type

import structlog
from pydantic import BaseModel

from structure_d.exceptions import InferenceError

if TYPE_CHECKING:
    from structure_d.config import Settings

logger = structlog.get_logger(__name__)


@dataclass
class ProviderResult:
    """
    Unified return value from :meth:`BaseLLMProvider.generate`.

    Carries the validated Pydantic model, the raw JSON text returned by the
    LLM, the model identifier that was actually used, and optional token-usage
    metrics so downstream components (metrics, ExtractionResult) always have a
    consistent data shape regardless of which provider was called.
    """

    output: BaseModel
    raw_text: str
    model_used: str
    token_usage: dict[str, int] = field(default_factory=dict)


class BaseLLMProvider(abc.ABC):
    """
    Abstract interface for LLM providers.

    Every concrete provider must implement two methods:

    * :meth:`generate` – structured output constrained to a Pydantic schema.
    * :meth:`generate_text` – free-form text generation (used by RAG/QA).
    """

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        """
        Generate structured output validated against *schema*.

        Args:
            prompt: User-facing text (document chunk, question, …).
            schema: Pydantic model class that defines the expected output shape.
            system_prompt: Optional system-level instruction.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens to generate.
            model: Override the provider's default model for this call.
            **kwargs: Provider-specific extras.

        Returns:
            :class:`ProviderResult` with a validated model instance, raw JSON
            text, model name used, and token-usage counts.
        """

    @abc.abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate free-form text (no schema constraint).

        Used by RAG query engines and other components that need plain prose
        rather than structured JSON.
        """


# ── OpenAI ────────────────────────────────────────────────────────────────────


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider. Requires ``openai>=1.0``."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        import os

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url

    def _get_client(self) -> Any:
        try:
            from openai import AsyncOpenAI  # type: ignore[reportMissingImports]
        except ImportError as e:
            raise ImportError(
                "openai>=1.0 is required for OpenAI provider. "
                "Install with: pip install openai"
            ) from e
        if not self.api_key:
            raise InferenceError("OPENAI_API_KEY must be set")
        return AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        client = self._get_client()
        effective_model = model or self.model

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.beta.chat.completions.parse(
                model=effective_model,
                messages=messages,
                response_format=schema,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise InferenceError("OpenAI returned an empty parsed response")

            raw_text = response.choices[0].message.content or json.dumps(parsed.model_dump())
            usage: dict[str, int] = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            return ProviderResult(
                output=parsed,
                raw_text=raw_text,
                model_used=effective_model,
                token_usage=usage,
            )
        except Exception as e:
            raise InferenceError(f"OpenAI API error: {e}") from e

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._get_client()
        effective_model = model or self.model

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await client.chat.completions.create(
                model=effective_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise InferenceError(f"OpenAI API error: {e}") from e


# ── Anthropic ─────────────────────────────────────────────────────────────────


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude API provider. Requires ``anthropic>=0.18``.

    Structured output is achieved via *tool use* (the only Anthropic-supported
    mechanism for schema-constrained generation).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        import os

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

    def _get_client(self) -> Any:
        try:
            import anthropic  # type: ignore[reportMissingImports]
        except ImportError as e:
            raise ImportError(
                "anthropic>=0.18 is required for Anthropic provider. "
                "Install with: pip install anthropic"
            ) from e
        if not self.api_key:
            raise InferenceError("ANTHROPIC_API_KEY must be set")
        return anthropic.AsyncAnthropic(api_key=self.api_key)

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        """
        Uses Anthropic tool-use to enforce the JSON schema.

        The model is forced to call a single tool whose ``input_schema``
        matches the Pydantic model's JSON Schema, guaranteeing a conformant
        response without prompt engineering.
        """
        client = self._get_client()
        effective_model = model or self.model
        json_schema = schema.model_json_schema()
        system = system_prompt or "You are a precise data extraction assistant."

        try:
            response = await client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[
                    {
                        "name": "extract_structured_data",
                        "description": "Extract structured data from the provided text.",
                        "input_schema": json_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": "extract_structured_data"},
                **kwargs,
            )

            # Find the tool-use content block
            data: dict[str, Any] = {}
            for block in response.content:
                if block.type == "tool_use":
                    data = block.input  # type: ignore[assignment]
                    break
            else:
                raise InferenceError(
                    "Anthropic did not return a tool-use block; "
                    "ensure the model supports tool use."
                )

            validated = schema.model_validate(data)
            raw_text = json.dumps(data)
            usage: dict[str, int] = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }
            return ProviderResult(
                output=validated,
                raw_text=raw_text,
                model_used=effective_model,
                token_usage=usage,
            )
        except Exception as e:
            raise InferenceError(f"Anthropic API error: {e}") from e

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._get_client()
        effective_model = model or self.model
        system = system_prompt or "You are a helpful assistant."

        try:
            response = await client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            return response.content[0].text if response.content else ""
        except Exception as e:
            raise InferenceError(f"Anthropic API error: {e}") from e


# ── Gemini ────────────────────────────────────────────────────────────────────


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider. Requires ``google-generativeai>=0.3``."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-1.5-pro",
    ) -> None:
        import os

        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model

    def _get_genai(self) -> Any:
        try:
            import google.generativeai as genai  # type: ignore[reportMissingImports]
        except ImportError as e:
            raise ImportError(
                "google-generativeai>=0.3 is required for Gemini provider. "
                "Install with: pip install google-generativeai"
            ) from e
        if not self.api_key:
            raise InferenceError("GOOGLE_API_KEY must be set")
        genai.configure(api_key=self.api_key)
        return genai

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        genai = self._get_genai()
        effective_model = model or self.model
        json_schema = schema.model_json_schema()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        try:
            gemini_model = genai.GenerativeModel(
                model_name=effective_model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "response_mime_type": "application/json",
                    "response_schema": json_schema,
                },
            )
            response = await gemini_model.generate_content_async(full_prompt)
            data = json.loads(response.text)
            validated = schema.model_validate(data)
            raw_text = response.text

            usage: dict[str, int] = {}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                meta = response.usage_metadata
                usage = {
                    "prompt_tokens": getattr(meta, "prompt_token_count", 0),
                    "completion_tokens": getattr(meta, "candidates_token_count", 0),
                    "total_tokens": getattr(meta, "total_token_count", 0),
                }
            return ProviderResult(
                output=validated,
                raw_text=raw_text,
                model_used=effective_model,
                token_usage=usage,
            )
        except Exception as e:
            raise InferenceError(f"Gemini API error: {e}") from e

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        genai = self._get_genai()
        effective_model = model or self.model
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        try:
            gemini_model = genai.GenerativeModel(
                model_name=effective_model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )
            response = await gemini_model.generate_content_async(full_prompt)
            return response.text
        except Exception as e:
            raise InferenceError(f"Gemini API error: {e}") from e


# ── Ollama ────────────────────────────────────────────────────────────────────


class OllamaProvider(BaseLLMProvider):
    """Ollama local-models provider. Uses ``httpx`` (bundled as a core dep)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
    ) -> None:
        self.base_url = base_url
        self.model = model

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        import httpx  # bundled core dep

        effective_model = model or self.model
        json_schema = schema.model_json_schema()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        schema_instruction = (
            f"\n\nReturn a valid JSON object matching this schema exactly:\n"
            f"{json.dumps(json_schema, indent=2)}"
        )

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": effective_model,
                        "prompt": full_prompt + schema_instruction,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                    timeout=120.0,
                )
                response.raise_for_status()
                result = response.json()
                raw_text = result["response"]
                data = json.loads(raw_text)
                validated = schema.model_validate(data)

                usage: dict[str, int] = {
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
                }
                return ProviderResult(
                    output=validated,
                    raw_text=raw_text,
                    model_used=effective_model,
                    token_usage=usage,
                )
            except Exception as e:
                raise InferenceError(f"Ollama API error: {e}") from e

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        import httpx

        effective_model = model or self.model
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": effective_model,
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                    timeout=120.0,
                )
                response.raise_for_status()
                return response.json()["response"]
            except Exception as e:
                raise InferenceError(f"Ollama API error: {e}") from e


# ── vLLM ──────────────────────────────────────────────────────────────────────


class VLLMProvider(BaseLLMProvider):
    """
    vLLM provider – wraps :class:`~structure_d.inference.vllm_client.VLLMClient`.

    Supports guided decoding (``guided_json``) for guaranteed schema-conformant
    output.  This is the default provider used by :class:`Pipeline` when no
    explicit provider is supplied.
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        from structure_d.inference.vllm_client import VLLMClient

        self.client = VLLMClient(api_base=api_base, api_key=api_key)
        self.model = model

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        from structure_d.config import get_settings

        settings = get_settings()
        effective_model = model or self.model or settings.models.default_model
        json_schema = schema.model_json_schema()

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat(
                model=effective_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_schema=json_schema,
                **{k: v for k, v in kwargs.items() if k != "model"},
            )
            raw_text = response["choices"][0]["message"]["content"]
            data = json.loads(raw_text)
            validated = schema.model_validate(data)

            usage: dict[str, int] = {}
            if "usage" in response:
                usage = {
                    "prompt_tokens": response["usage"].get("prompt_tokens", 0),
                    "completion_tokens": response["usage"].get("completion_tokens", 0),
                    "total_tokens": response["usage"].get("total_tokens", 0),
                }
            return ProviderResult(
                output=validated,
                raw_text=raw_text,
                model_used=effective_model,
                token_usage=usage,
            )
        except Exception as e:
            raise InferenceError(f"vLLM API error: {e}") from e

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        from structure_d.config import get_settings

        settings = get_settings()
        effective_model = model or self.model or settings.models.default_model

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat(
                model=effective_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            raise InferenceError(f"vLLM API error: {e}") from e


# ── Fallback provider ─────────────────────────────────────────────────────────


class FallbackProvider(BaseLLMProvider):
    """
    Wraps a *primary* and a *fallback* provider.

    Every call is attempted on ``primary`` first.  If ``primary`` raises an
    :class:`~structure_d.exceptions.InferenceError` (e.g. vLLM not reachable,
    network timeout, HTTP 5xx), the same call is transparently retried on
    ``fallback`` and a warning is logged.

    Typical use-case::

        # Try your local vLLM server; fall back to Anthropic when it is down.
        provider = FallbackProvider(
            primary=VLLMProvider(),
            fallback=AnthropicProvider(),
        )
        pipeline = Pipeline(schema_cls=MySchema, provider=provider)

    The fallback is **not** triggered for validation or Pydantic errors – only
    for :class:`InferenceError` raised by the underlying HTTP/SDK call.
    """

    def __init__(
        self,
        primary: BaseLLMProvider,
        fallback: BaseLLMProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        try:
            return await self.primary.generate(
                prompt=prompt,
                schema=schema,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
                **kwargs,
            )
        except InferenceError as exc:
            # Primary failed – log and hand off to the fallback provider.
            logger.warning(
                "primary_provider_failed_falling_back",
                primary=type(self.primary).__name__,
                fallback=type(self.fallback).__name__,
                error=str(exc),
            )
            return await self.fallback.generate(
                prompt=prompt,
                schema=schema,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
                **kwargs,
            )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            return await self.primary.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
                **kwargs,
            )
        except InferenceError as exc:
            logger.warning(
                "primary_provider_failed_falling_back",
                primary=type(self.primary).__name__,
                fallback=type(self.fallback).__name__,
                error=str(exc),
            )
            return await self.fallback.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
                **kwargs,
            )


# ── Factory ───────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "vllm": VLLMProvider,
}


def get_provider(name: str, **kwargs: object) -> BaseLLMProvider:
    """Instantiate a provider by name.

    Example::

        provider = get_provider("openai", api_key="sk-...", model="gpt-4o")
        provider = get_provider("vllm", api_base="http://localhost:8000/v1")
    """
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(_PROVIDERS)}")
    return cls(**kwargs)  # type: ignore[arg-type]


def _build_provider_from_config(name: str, settings: Settings) -> BaseLLMProvider:
    """Build a single concrete provider from the named config section."""
    pc = settings.inference.provider
    if name == "vllm":
        return VLLMProvider(
            api_base=pc.vllm.api_base,
            api_key=pc.vllm.api_key,
        )
    if name == "openai":
        return OpenAIProvider(
            api_key=pc.openai.api_key,
            model=pc.openai.model,
            base_url=pc.openai.base_url,
        )
    if name == "anthropic":
        return AnthropicProvider(
            api_key=pc.anthropic.api_key,
            model=pc.anthropic.model,
        )
    if name == "gemini":
        return GeminiProvider(
            api_key=pc.gemini.api_key,
            model=pc.gemini.model,
        )
    if name == "ollama":
        return OllamaProvider(
            base_url=pc.ollama.base_url,
            model=pc.ollama.model,
        )
    raise ValueError(f"Unknown provider name in config: {name!r}")


def resolve_provider(settings: Settings) -> BaseLLMProvider:
    """
    Build the configured LLM provider (or a :class:`FallbackProvider` chain)
    from ``settings.inference.provider``.

    Reads two config keys:

    * ``inference.provider.provider`` – primary provider (default: ``"vllm"``).
    * ``inference.provider.fallback_provider`` – optional fallback provider name.

    When ``fallback_provider`` is set (e.g. ``"anthropic"``), returns a
    :class:`FallbackProvider` that transparently falls back whenever the
    primary raises an :class:`~structure_d.exceptions.InferenceError`.

    Example (``configs/default.yaml``)::

        inference:
          provider:
            provider: "vllm"
            fallback_provider: "anthropic"   # used when vLLM is unreachable
            anthropic:
              model: "claude-3-5-sonnet-20241022"
              api_key: null                  # reads ANTHROPIC_API_KEY from env

    Example (Python)::

        from structure_d.config import get_settings
        from structure_d.inference.providers import resolve_provider

        provider = resolve_provider(get_settings())
        pipeline = Pipeline(schema_cls=MySchema, provider=provider)
    """
    primary = _build_provider_from_config(settings.inference.provider.provider, settings)

    fallback_name = settings.inference.provider.fallback_provider
    if not fallback_name:
        return primary

    fallback = _build_provider_from_config(fallback_name, settings)
    logger.info(
        "provider_fallback_configured",
        primary=settings.inference.provider.provider,
        fallback=fallback_name,
    )
    return FallbackProvider(primary=primary, fallback=fallback)
