"""
Retrieval-Augmented Generation pipeline.

Delegates to the indexing layer (VectorStoreIndex + QueryEngine)
for a single implementation and consistent behaviour.
"""

from __future__ import annotations

from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.inference.vllm_client import VLLMClient
from structure_d.retrieval.embeddings import EmbeddingService
from structure_d.retrieval.vector_store import VectorStoreBase
from structure_d.schemas.base import TextChunk

logger = structlog.get_logger(__name__)


class RAGPipeline:
    """
    End-to-end RAG: embed query → retrieve → compose prompt → generate.

    Uses :class:`structure_d.indexing.VectorStoreIndex` and
    :class:`structure_d.indexing.QueryEngine` under the hood.

    Usage::

        rag = RAGPipeline(vector_store=my_store, embedding_service=my_emb)
        await rag.index_chunks(chunks)
        answer = await rag.query("What is the total amount?", model="llama-3.1-8b")
    """

    def __init__(
        self,
        vector_store: VectorStoreBase,
        embedding_service: EmbeddingService | None = None,
        client: VLLMClient | None = None,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> None:
        settings = get_settings()
        self.vector_store = vector_store
        self.embedding_service = embedding_service or EmbeddingService()
        self.client = client or VLLMClient()
        self.top_k = top_k or settings.retrieval.top_k
        self.similarity_threshold = similarity_threshold or settings.retrieval.similarity_threshold
        self._index: Any = None

    def _get_index(self) -> Any:
        """Lazy-build vector index for indexing/retrieval."""
        if self._index is None:
            from structure_d.indexing import VectorStoreIndex

            self._index = VectorStoreIndex(
                vector_store=self.vector_store,
                embedding_service=self.embedding_service,
                similarity_threshold=self.similarity_threshold,
            )
        return self._index

    # ── Indexing ──────────────────────────────────────────────────────────────

    async def index_chunks(self, chunks: list[TextChunk]) -> None:
        """Embed and store chunks in the vector store (via VectorStoreIndex)."""
        from structure_d.indexing.documents import Node

        nodes = [Node.from_text_chunk(c) for c in chunks]
        index = self._get_index()
        await index.insert_nodes(nodes)
        logger.info("rag_indexed", count=len(chunks))

    # ── Querying ──────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Embed *query* and retrieve relevant chunks (returns list of dicts for compatibility)."""
        index = self._get_index()
        retriever = index.as_retriever(
            top_k=top_k or self.top_k,
            similarity_threshold=self.similarity_threshold,
        )
        nodes = await retriever.retrieve(query, top_k=top_k or self.top_k, filter_metadata=filter_metadata)
        return [n.to_retrieval_result() for n in nodes]

    async def query(
        self,
        question: str,
        model: str,
        *,
        top_k: int | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        system_prompt: str | None = None,
    ) -> str:
        """Full RAG: retrieve context, compose prompt, generate answer (via QueryEngine)."""
        index = self._get_index()
        retriever = index.as_retriever(top_k=top_k or self.top_k)
        from structure_d.indexing import QueryEngine

        engine = QueryEngine(
            retriever=retriever,
            llm_client=self.client,
            response_mode="simple",
            top_k=top_k or self.top_k,
            system_prompt=system_prompt,
        )
        return await engine.query(
            question,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
