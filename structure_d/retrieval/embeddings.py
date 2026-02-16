"""Embedding generation for RAG pipelines."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from structure_d.config import get_settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """
    Generate embeddings using either:
    - A local SentenceTransformers model, or
    - The vLLM / OpenAI-compatible embeddings endpoint.
    """

    def __init__(
        self,
        model_name: str | None = None,
        use_api: bool = False,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.models.embedding_model
        self.use_api = use_api
        self.api_base = api_base or settings.inference.vllm.api_base
        self.api_key = api_key or settings.inference.vllm.api_key
        self._local_model = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        if self.use_api:
            return await self._embed_api(texts)
        return await self._embed_local(texts)

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]

    # ── Local (SentenceTransformers) ──────────────────────────────────────────

    def _load_local(self) -> Any:
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._local_model = SentenceTransformer(self.model_name)
            except ImportError as e:
                raise ImportError(
                    "Local embeddings require sentence-transformers. "
                    "Install with: pip install structure-d[retrieval]"
                ) from e
        return self._local_model

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        model = self._load_local()
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: model.encode(texts, normalize_embeddings=True).tolist()
        )
        return embeddings

    # ── API-based ─────────────────────────────────────────────────────────────

    async def _embed_api(self, texts: list[str]) -> list[list[float]]:
        import httpx

        url = f"{self.api_base.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {"model": self.model_name, "input": texts}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return [item["embedding"] for item in data["data"]]
