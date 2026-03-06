"""
Base index and retriever interfaces.

Indexes store Nodes and expose Retrievers; Query Engines use Retrievers
plus response synthesis for RAG.
"""

from __future__ import annotations

import abc
from typing import Any

from structure_d.indexing.documents import Node


class BaseRetriever(abc.ABC):
    """Interface for retrieving relevant nodes given a query."""

    @abc.abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Node]:
        """Return top-k nodes most relevant to the query."""
        ...


class BaseIndex(abc.ABC):
    """
    Data structure that stores Nodes and supports retrieval.

    Subclasses implement different backends: vector store, in-memory summary, etc.
    """

    @abc.abstractmethod
    async def insert_nodes(self, nodes: list[Node]) -> None:
        """Insert nodes into the index."""
        ...

    @abc.abstractmethod
    def as_retriever(self, **kwargs: Any) -> BaseRetriever:
        """Return a retriever over this index."""
        ...

    def as_query_engine(
        self,
        *,
        provider: Any = None,
        response_mode: str = "simple",
        top_k: int = 5,
        **kwargs: Any,
    ) -> Any:
        """Build a query engine from this index (requires indexing.query_engine)."""
        from structure_d.indexing.query_engine import QueryEngine

        retriever = self.as_retriever(top_k=top_k, **kwargs)
        return QueryEngine(
            retriever=retriever,
            provider=provider,
            response_mode=response_mode,
            top_k=top_k,
        )
