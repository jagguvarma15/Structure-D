"""Summary (list) index: in-memory nodes, retrieve all or by filter."""

from __future__ import annotations

from typing import Any

import structlog

from structure_d.indexing.base import BaseIndex, BaseRetriever
from structure_d.indexing.documents import Node

logger = structlog.get_logger(__name__)


class SummaryRetriever(BaseRetriever):
    """Retriever over in-memory nodes: returns all or top_k by optional metadata filter."""

    def __init__(self, nodes: list[Node], top_k: int = 10) -> None:
        self._nodes = list(nodes)
        self.top_k = top_k

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[Node]:
        subset = self._nodes
        if filter_metadata:
            subset = [
                n for n in subset
                if all(n.metadata.get(k) == v for k, v in filter_metadata.items())
            ]
        k = top_k if top_k > 0 else self.top_k
        return subset[:k]


class SummaryIndex(BaseIndex):
    """
    In-memory index that stores nodes in a list (no embeddings).

    Good for small corpora or when you want to pass full context to the LLM.
    """

    def __init__(self, nodes: list[Node] | None = None) -> None:
        self._nodes: list[Node] = list(nodes) if nodes else []

    async def insert_nodes(self, nodes: list[Node]) -> None:
        self._nodes.extend(nodes)
        logger.debug("summary_index_inserted", count=len(nodes), total=len(self._nodes))

    def as_retriever(self, top_k: int = 10, **kwargs: Any) -> BaseRetriever:
        return SummaryRetriever(nodes=self._nodes, top_k=top_k)
