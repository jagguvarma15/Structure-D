"""Vector store abstraction."""

from __future__ import annotations

import abc
import json
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
    PostgreSQL + pgvector backend using asyncpg.
    
    Requires: ``pip install structure-d[storage]`` (includes asyncpg + pgvector)
    
    The store uses a table named ``embeddings`` with the following schema:
    - id: VARCHAR PRIMARY KEY
    - embedding: vector(embedding_dimension)
    - document: TEXT
    - metadata: JSONB
    - created_at: TIMESTAMP
    """

    def __init__(
        self,
        connection_string: str | None = None,
        table_name: str = "embeddings",
        embedding_dimension: int | None = None,
    ) -> None:
        settings = get_settings()
        self.connection_string = connection_string or settings.retrieval.pgvector.connection_string
        self.table_name = table_name
        self.embedding_dimension = embedding_dimension or settings.retrieval.embedding_dimension
        self._pool = None

    async def _ensure_pool(self) -> Any:
        """Create connection pool if it doesn't exist."""
        if self._pool is not None:
            return self._pool
        
        try:
            import asyncpg
        except ImportError as e:
            raise ImportError(
                "PGVectorStore requires asyncpg. Install with: pip install structure-d[storage]"
            ) from e
        
        # Parse connection string (remove +asyncpg if present)
        conn_str = self.connection_string.replace("+asyncpg", "")
        
        self._pool = await asyncpg.create_pool(conn_str, min_size=1, max_size=10)
        
        # Ensure pgvector extension and table exist
        async with self._pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Create table if it doesn't exist
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id VARCHAR PRIMARY KEY,
                    embedding vector({self.embedding_dimension}),
                    document TEXT NOT NULL,
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index for vector similarity search
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx 
                ON {self.table_name} 
                USING ivfflat (embedding vector_cosine_ops)
            """)
        
        logger.info("pgvector_initialized", table=self.table_name, dimension=self.embedding_dimension)
        return self._pool

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert documents with their embeddings."""
        pool = await self._ensure_pool()
        
        if metadatas is None:
            metadatas = [{}] * len(ids)
        
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("ids, embeddings, documents, and metadatas must have the same length")

        async with pool.acquire() as conn:
            for doc_id, embedding, doc, meta in zip(ids, embeddings, documents, metadatas):
                if len(embedding) != self.embedding_dimension:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                        f"got {len(embedding)}"
                    )
                
                await conn.execute(
                    f"""
                    INSERT INTO {self.table_name} (id, embedding, document, metadata)
                    VALUES ($1, $2::vector, $3, $4::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        document = EXCLUDED.document,
                        metadata = EXCLUDED.metadata
                    """,
                    doc_id,
                    str(embedding),  # Convert to string for vector type
                    doc,
                    json.dumps(meta),
                )
        
        logger.debug("pgvector_add", count=len(ids))

    async def query(
        self,
        embedding: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k most similar documents using cosine similarity."""
        pool = await self._ensure_pool()
        
        if len(embedding) != self.embedding_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                f"got {len(embedding)}"
            )
        
        # Build query with optional metadata filter
        query = f"""
            SELECT 
                id,
                document,
                metadata,
                1 - (embedding <=> $1::vector) as distance
            FROM {self.table_name}
        """
        
        params: list[Any] = [str(embedding)]
        
        if filter_metadata:
            # Add JSONB filter conditions
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"metadata->>'{key}' = ${len(params) + 1}")
                params.append(str(value))
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        query += f" ORDER BY embedding <=> $1::vector LIMIT ${len(params) + 1}"
        params.append(top_k)
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return [
            {
                "id": row["id"],
                "document": row["document"],
                "metadata": row["metadata"] if isinstance(row["metadata"], dict) else {},
                "distance": float(row["distance"]) if row["distance"] is not None else None,
            }
            for row in rows
        ]

    async def delete(self, ids: list[str]) -> None:
        """Delete documents by ID."""
        pool = await self._ensure_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                f"DELETE FROM {self.table_name} WHERE id = ANY($1::text[])",
                ids,
            )
        
        logger.debug("pgvector_delete", count=len(ids))
    
    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
