"""Vector store index: embed nodes and retrieve by similarity."""

from __future__ import annotations

from typing import Any

import structlog

from structure_d.indexing.base import BaseIndex, BaseRetriever
from structure_d.indexing.documents import Node
from structure_d.retrieval.embeddings import EmbeddingService
from structure_d.retrieval.vector_store import VectorStoreBase

logger = structlog.get_logger(__name__)


class VectorStoreRetriever(BaseRetriever):
    """Retriever that embeds the query and runs similarity search."""

    def __init__(
        self,
        vector_store: VectorStoreBase,
        embedding_service: EmbeddingService,
        top_k: int = 5,
        similarity_threshold: float | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Node]:
        k = top_k if top_k > 0 else self.top_k
        embedding = await self.embedding_service.embed_one(query)
        results = await self.vector_store.query(
            embedding=embedding,
            top_k=k,
            filter_metadata=filter_metadata,
        )
        nodes: list[Node] = []
        for r in results:
            doc_text = r.get("document", "")
            if self.similarity_threshold is not None:
                dist = r.get("distance")
                if dist is not None and dist > (1 - self.similarity_threshold):
                    continue
            nodes.append(
                Node(
                    id=r.get("id", ""),
                    text=doc_text,
                    document_id=r.get("metadata", {}).get("document_id", ""),
                    metadata=r.get("metadata") or {},
                    extra={"distance": r.get("distance")},
                )
            )
        return nodes


class VectorStoreIndex(BaseIndex):
    """
    Index that stores nodes in a vector store with embeddings.

    Usage::

        index = VectorStoreIndex(vector_store=store, embedding_service=emb)
        await index.insert_nodes(nodes)
        retriever = index.as_retriever(top_k=5)
        nodes = await retriever.retrieve("What is the total amount?")
    """

    def __init__(
        self,
        vector_store: VectorStoreBase,
        embedding_service: EmbeddingService | None = None,
        similarity_threshold: float | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service or EmbeddingService()
        self.similarity_threshold = similarity_threshold

    async def insert_nodes(self, nodes: list[Node]) -> None:
        if not nodes:
            return
        texts = [n.text for n in nodes]
        ids = [n.id for n in nodes]
        metadatas = [
            {"document_id": n.document_id, **n.metadata}
            for n in nodes
        ]
        embeddings = await self.embedding_service.embed(texts)
        await self.vector_store.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("vector_index_inserted", count=len(nodes))

    def as_retriever(
        self,
        top_k: int = 5,
        similarity_threshold: float | None = None,
        **kwargs: Any,
    ) -> BaseRetriever:
        return VectorStoreRetriever(
            vector_store=self.vector_store,
            embedding_service=self.embedding_service,
            top_k=top_k,
            similarity_threshold=similarity_threshold or self.similarity_threshold,
        )
