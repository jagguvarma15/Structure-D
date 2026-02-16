"""Retrieval-Augmented Generation pipeline."""

from __future__ import annotations

from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.inference.vllm_client import VLLMClient
from structure_d.retrieval.embeddings import EmbeddingService
from structure_d.retrieval.vector_store import VectorStoreBase
from structure_d.schemas.base import TextChunk

logger = structlog.get_logger(__name__)

_RAG_SYSTEM_PROMPT = """\
You are a helpful assistant. Use the context below to answer the user's question.
If the answer is not in the context, say so.

## Context
{context}
"""


class RAGPipeline:
    """
    End-to-end RAG: embed query → retrieve → compose prompt → generate.

    Usage::

        rag = RAGPipeline(vector_store=my_store, embedding_service=my_emb)
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

    # ── Indexing ──────────────────────────────────────────────────────────────

    async def index_chunks(self, chunks: list[TextChunk]) -> None:
        """Embed and store chunks in the vector store."""
        texts = [c.text for c in chunks]
        ids = [c.metadata.chunk_id for c in chunks]
        metadatas = [
            {
                "document_id": c.metadata.document_id,
                "heading": c.metadata.heading or "",
                "page_number": c.metadata.page_number or 0,
            }
            for c in chunks
        ]

        embeddings = await self.embedding_service.embed(texts)
        await self.vector_store.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("rag_indexed", count=len(chunks))

    # ── Querying ──────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Embed *query* and retrieve relevant chunks."""
        embedding = await self.embedding_service.embed_one(query)
        results = await self.vector_store.query(
            embedding=embedding,
            top_k=top_k or self.top_k,
            filter_metadata=filter_metadata,
        )
        # Filter by similarity threshold
        if self.similarity_threshold:
            results = [
                r for r in results
                if r.get("distance") is None or r["distance"] <= (1 - self.similarity_threshold)
            ]
        return results

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
        """Full RAG: retrieve context, compose prompt, generate answer."""
        retrieved = await self.retrieve(question, top_k=top_k)

        context = "\n\n---\n\n".join(
            r.get("document", "") for r in retrieved
        )
        sys_prompt = (system_prompt or _RAG_SYSTEM_PROMPT).format(context=context)

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": question},
        ]

        response = await self.client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choices = response.get("choices", [])
        return choices[0].get("message", {}).get("content", "") if choices else ""
