"""Vector store abstraction."""

from __future__ import annotations

import abc
from typing import Any

import structlog

from structure_d.config import get_settings

logger = structlog.get_logger(__name__)


class VectorStoreBase(abc.ABC):
    """Interface for vector databases."""

    @abc.abstractmethod
    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert documents with their embeddings."""

    @abc.abstractmethod
    async def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k most similar documents."""

    @abc.abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete documents by ID."""


class ChromaVectorStore(VectorStoreBase):
    """
    Chroma vector store backend.

    Requires: ``pip install chromadb``
    """

    def __init__(
        self,
        collection_name: str = "structure_d",
        persist_directory: str | None = None,
    ) -> None:
        settings = get_settings()
        self.persist_directory = persist_directory or settings.retrieval.chroma.persist_directory
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _ensure_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=self.persist_directory)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except ImportError as e:
            raise ImportError(
                "ChromaDB is required. Install with: pip install structure-d[retrieval]"
            ) from e

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        col = self._ensure_collection()
        col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug("chroma_add", count=len(ids))

    async def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        col = self._ensure_collection()
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": top_k,
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        results = col.query(**kwargs)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {
                "id": ids[i],
                "document": docs[i],
                "metadata": metas[i] if metas else {},
                "distance": distances[i] if distances else None,
            }
            for i in range(len(docs))
        ]

    async def delete(self, ids: list[str]) -> None:
        col = self._ensure_collection()
        col.delete(ids=ids)


class PGVectorStore(VectorStoreBase):
    """
    PostgreSQL + pgvector backend (placeholder – production code would
    use asyncpg / SQLAlchemy with the pgvector extension).
    """

    def __init__(self, connection_string: str | None = None) -> None:
        settings = get_settings()
        self.connection_string = connection_string or settings.retrieval.pgvector.connection_string

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        raise NotImplementedError(
            "PGVectorStore.add() requires asyncpg + pgvector. "
            "Implement with your own SQL schema."
        )

    async def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("PGVectorStore.query() not yet implemented.")

    async def delete(self, ids: list[str]) -> None:
        raise NotImplementedError("PGVectorStore.delete() not yet implemented.")
