"""Multi-LLM provider support: OpenAI, Anthropic, Gemini, Ollama, vLLM."""

from __future__ import annotations

import abc
import json
from typing import Any, Type

from pydantic import BaseModel

from structure_d.exceptions import InferenceError


class BaseLLMProvider(abc.ABC):
    """Interface for LLM providers."""

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> BaseModel:
        """
        Generate structured output from a prompt.

        Args:
            prompt: User prompt
            schema: Pydantic model for structured output
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific options

        Returns:
            Validated Pydantic model instance
        """


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

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> BaseModel:
        try:
            from openai import OpenAI  # type: ignore[reportMissingImports]
        except ImportError as e:
            raise ImportError(
                "openai>=1.0 is required for OpenAI provider. Install with: pip install openai"
            ) from e

        if not self.api_key:
            raise InferenceError("OPENAI_API_KEY must be set")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=schema,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise InferenceError("Failed to parse response")
            return parsed
        except Exception as e:
            raise InferenceError(f"OpenAI API error: {e}") from e


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider. Requires ``anthropic>=0.18``."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        import os

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> BaseModel:
        try:
            import anthropic  # type: ignore[reportMissingImports]
        except ImportError as e:
            raise ImportError(
                "anthropic>=0.18 is required for Anthropic provider. "
                "Install with: pip install anthropic"
            ) from e

        if not self.api_key:
            raise InferenceError("ANTHROPIC_API_KEY must be set")

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        json_schema = schema.model_json_schema()
        system = system_prompt or "You are a helpful assistant that returns structured JSON."

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_schema", "json_schema": json_schema},
                **kwargs,
            )

            content = response.content[0].text
            data = json.loads(content)
            return schema.model_validate(data)
        except Exception as e:
            raise InferenceError(f"Anthropic API error: {e}") from e


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

    async def generate(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> BaseModel:
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

        json_schema = schema.model_json_schema()
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            model = genai.GenerativeModel(
                model_name=self.model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "response_mime_type": "application/json",
                    "response_schema": json_schema,
                },
            )

            response = await model.generate_content_async(full_prompt)
            data = json.loads(response.text)
            return schema.model_validate(data)
        except Exception as e:
            raise InferenceError(f"Gemini API error: {e}") from e


class OllamaProvider(BaseLLMProvider):
    """Ollama local models provider. Requires ``ollama`` package."""

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
        **kwargs: Any,
    ) -> BaseModel:
        try:
            import httpx  # type: ignore[reportMissingImports]
        except ImportError:
            raise ImportError("httpx is required for Ollama provider") from None

        json_schema = schema.model_json_schema()
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        schema_instruction = f"\n\nReturn a valid JSON object matching this schema: {json_schema}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": full_prompt + schema_instruction,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                    timeout=120.0,
                )
                response.raise_for_status()
                result = response.json()
                data = json.loads(result["response"])
                return schema.model_validate(data)
            except Exception as e:
                raise InferenceError(f"Ollama API error: {e}") from e


class VLLMProvider(BaseLLMProvider):
    """vLLM provider (existing implementation)."""

    def __init__(
        self,
        api_base: str = "http://localhost:8000/v1",
        api_key: str = "EMPTY",
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
        **kwargs: Any,
    ) -> BaseModel:
        from structure_d.config import get_settings

        settings = get_settings()
        model = self.model or kwargs.get("model") or settings.models.default_model

        json_schema = schema.model_json_schema()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_schema=json_schema,
            **{k: v for k, v in kwargs.items() if k != "model"},
        )

        # Extract content from response
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)
        return schema.model_validate(data)


# ── Factory ───────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "vllm": VLLMProvider,
}


def get_provider(name: str, **kwargs: object) -> BaseLLMProvider:
    """Instantiate a provider by name."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(_PROVIDERS)}")
    return cls(**kwargs)  # type: ignore[arg-type]
