#!/usr/bin/env python3
"""
Example: Indexing and querying over documents.

Load → Documents/Nodes → Index → Retriever → QueryEngine.
Works with a single file or a directory.

Usage:
    # Vector index (embeddings + similarity search)
    python examples/llama_index_style_rag.py vector path/to/doc.pdf "Your question?"

    # Summary index (in-memory, no embeddings)
    python examples/llama_index_style_rag.py summary path/to/doc.pdf "Your question?"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure_d.config import get_settings
from structure_d.indexing import DocumentReader, QueryEngine, SummaryIndex, VectorStoreIndex
from structure_d.inference.vllm_client import VLLMClient
from structure_d.monitoring.logging import setup_logging
from structure_d.retrieval.embeddings import EmbeddingService
from structure_d.retrieval.vector_store import ChromaVectorStore


async def run_vector(path: Path, question: str) -> None:
    """Load file, build vector index, and query."""
    reader = DocumentReader()
    nodes = await reader.load_and_chunk(path)
    print(f"Loaded {len(nodes)} nodes from {path.name}")

    vector_store = ChromaVectorStore(collection_name="llama_style_example")
    embedding_service = EmbeddingService()
    index = VectorStoreIndex(
        vector_store=vector_store,
        embedding_service=embedding_service,
    )
    await index.insert_nodes(nodes)
    print("Vector index built.")

    retriever = index.as_retriever(top_k=5)
    engine = QueryEngine(
        retriever=retriever,
        llm_client=VLLMClient(),
        response_mode="compact",
    )
    answer = await engine.query(question, model=get_settings().models.default_model)
    print(f"\nQ: {question}\nA: {answer}")


async def run_summary(path: Path, question: str) -> None:
    """Load file, build summary index (in-memory), and query."""
    reader = DocumentReader()
    nodes = await reader.load_and_chunk(path)
    print(f"Loaded {len(nodes)} nodes from {path.name}")

    index = SummaryIndex(nodes=nodes)
    retriever = index.as_retriever(top_k=5)
    engine = QueryEngine(
        retriever=retriever,
        llm_client=VLLMClient(),
        response_mode="compact",
    )
    answer = await engine.query(question, model=get_settings().models.default_model)
    print(f"\nQ: {question}\nA: {answer}")


async def main() -> None:
    setup_logging(log_format="console")
    if len(sys.argv) < 4:
        print(
            "Usage: python examples/llama_index_style_rag.py <vector|summary> <path> \"question\""
        )
        sys.exit(1)
    index_type, path_str, question = sys.argv[1], sys.argv[2], sys.argv[3]
    path = Path(path_str)
    if not path.exists():
        print(f"Path not found: {path}")
        sys.exit(1)
    if index_type == "vector":
        await run_vector(path, question)
    elif index_type == "summary":
        await run_summary(path, question)
    else:
        print("index_type must be 'vector' or 'summary'")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
