"""Async vLLM client using the OpenAI-compatible API."""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from structure_d.config import get_settings

logger = structlog.get_logger(__name__)


class VLLMClient:
    """
    Thin async wrapper around vLLM's OpenAI-compatible chat/completions API.

    Supports:
    - Chat completions with structured outputs (JSON schema / regex / choice / grammar).
    - Streaming responses.
    - Automatic retries with exponential back-off.

    Usage::

        client = VLLMClient()
        result = await client.chat(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=[{"role": "user", "content": "Extract ..."}],
            json_schema=my_schema,
        )
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.api_base = (api_base or settings.inference.vllm.api_base).rstrip("/")
        self.api_key = api_key or settings.inference.vllm.api_key
        self.timeout = timeout or settings.inference.vllm.timeout_seconds
        self.max_retries = max_retries or settings.inference.vllm.max_retries

    # ── Public API ────────────────────────────────────────────────────────────

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_schema: dict[str, Any] | None = None,
        regex_pattern: str | None = None,
        choice: list[str] | None = None,
        grammar: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a chat completion request to vLLM.

        Structured output parameters are mutually exclusive; pass at most one of
        *json_schema*, *regex_pattern*, *choice* or *grammar*.

        Returns the full API response dict.
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Build structured_outputs / guided decoding
        structured = self._build_structured_params(json_schema, regex_pattern, choice, grammar)
        if structured:
            body["extra_body"] = {**(extra_body or {}), **structured}
        elif extra_body:
            body["extra_body"] = extra_body

        return await self._post("/chat/completions", body)

    async def completions(
        self,
        model: str,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_schema: dict[str, Any] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a plain /completions request to vLLM."""
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        structured = self._build_structured_params(json_schema, None, None, None)
        if structured:
            body["extra_body"] = {**(extra_body or {}), **structured}
        elif extra_body:
            body["extra_body"] = extra_body

        return await self._post("/completions", body)

    async def list_models(self) -> list[dict[str, Any]]:
        """Query /v1/models endpoint."""
        resp = await self._get("/models")
        return resp.get("data", [])

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_structured_params(
        json_schema: dict[str, Any] | None,
        regex_pattern: str | None,
        choice: list[str] | None,
        grammar: str | None,
    ) -> dict[str, Any]:
        """Translate convenience args into vLLM's guided_* parameters."""
        params: dict[str, Any] = {}
        if json_schema:
            params["guided_json"] = json_schema
        elif regex_pattern:
            params["guided_regex"] = regex_pattern
        elif choice:
            params["guided_choice"] = choice
        elif grammar:
            params["guided_grammar"] = grammar
        return params

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=body, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    elapsed = (time.monotonic() - t0) * 1000
                    logger.debug(
                        "vllm_request",
                        path=path,
                        model=body.get("model"),
                        latency_ms=round(elapsed, 1),
                        status=resp.status_code,
                    )
                    return data
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "vllm_request_retry",
                    attempt=attempt,
                    wait=wait,
                    error=str(exc),
                )
                import asyncio

                await asyncio.sleep(wait)

        raise RuntimeError(
            f"vLLM request failed after {self.max_retries} retries"
        ) from last_exc

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
