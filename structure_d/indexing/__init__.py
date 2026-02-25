"""
LlamaIndex-inspired indexing: Documents, Nodes, Indexes, QueryEngine.

Data flow: load (Reader) → Documents → transform to Nodes → Index → Retriever → QueryEngine.
"""

from structure_d.indexing.base import BaseIndex, BaseRetriever
from structure_d.indexing.documents import Document, Node
from structure_d.indexing.loading import DocumentReader
from structure_d.indexing.query_engine import QueryEngine, ResponseSynthesizer
from structure_d.indexing.summary_index import SummaryIndex, SummaryRetriever
from structure_d.indexing.vector_index import VectorStoreIndex, VectorStoreRetriever

__all__ = [
    "BaseIndex",
    "BaseRetriever",
    "Document",
    "DocumentReader",
    "Node",
    "QueryEngine",
    "ResponseSynthesizer",
    "SummaryIndex",
    "SummaryRetriever",
    "VectorStoreIndex",
    "VectorStoreRetriever",
]
