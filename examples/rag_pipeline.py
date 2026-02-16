#!/usr/bin/env python3
"""
Example: RAG pipeline – index documents of any format and ask questions.

Usage:
    python examples/rag_pipeline.py path/to/docs/ "What is the main topic?"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure_d.config import get_settings
from structure_d.ingestion.manager import IngestionManager
from structure_d.monitoring.logging import setup_logging
from structure_d.preprocessing.chunker import Chunker
from structure_d.preprocessing.normalizer import normalize_text
from structure_d.retrieval.embeddings import EmbeddingService
from structure_d.retrieval.rag_pipeline import RAGPipeline
from structure_d.retrieval.vector_store import ChromaVectorStore
from structure_d.schemas.base import TextChunk


async def main(docs_dir: str, question: str) -> None:
    setup_logging(log_format="console")
    settings = get_settings()

    # 1. Ingest all documents (any supported format)
    manager = IngestionManager()
    docs_path = Path(docs_dir)
    files = sorted(
        f for f in docs_path.rglob("*")
        if f.is_file() and f.suffix.lower() in settings.ingestion.supported_extensions
    )

    print(f"Found {len(files)} files to index.")

    chunker = Chunker()
    all_chunks: list[TextChunk] = []

    for fp in files:
        doc = await manager.ingest(fp)
        text = normalize_text(doc.text)
        chunks = chunker.chunk(text, document_id=doc.metadata.document_id)
        all_chunks.extend(chunks)
        print(f"  [{doc.metadata.format.value:15s}] {fp.name}: {len(chunks)} chunks")

    # 2. Set up RAG pipeline
    vector_store = ChromaVectorStore(collection_name="rag_example")
    embedding_service = EmbeddingService()
    rag = RAGPipeline(
        vector_store=vector_store,
        embedding_service=embedding_service,
    )

    # 3. Index chunks
    print(f"\nIndexing {len(all_chunks)} chunks...")
    await rag.index_chunks(all_chunks)

    # 4. Query
    print(f"\nQuestion: {question}")
    model = settings.models.default_model
    answer = await rag.query(question, model=model)
    print(f"\nAnswer: {answer}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python examples/rag_pipeline.py <docs_dir> "question"')
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
