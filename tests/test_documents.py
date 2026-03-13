"""Tests for Document and Node model conversions."""

from __future__ import annotations

from structure_d.indexing.documents import Document, Node
from structure_d.schemas.base import (
    ChunkMetadata,
    DocumentFormat,
    DocumentMetadata,
    ParsedDocument,
    TextChunk,
)


def test_document_from_parsed(parsed_document: ParsedDocument):
    """Document.from_parsed should map id, text, and metadata correctly."""
    doc = Document.from_parsed(parsed_document)

    assert doc.id == parsed_document.metadata.document_id
    assert doc.text == parsed_document.text
    assert doc.metadata["filename"] == "sample.txt"
    assert doc.extra["format"] == str(DocumentFormat.PLAIN_TEXT)


def test_node_from_text_chunk(text_chunk: TextChunk):
    """Node.from_text_chunk should map id, text, document_id, and metadata."""
    node = Node.from_text_chunk(text_chunk)

    assert node.id == text_chunk.metadata.chunk_id
    assert node.text == text_chunk.text
    assert node.document_id == text_chunk.metadata.document_id
    assert "chunk_id" in node.metadata


def test_node_to_retrieval_result_with_score():
    """to_retrieval_result with a score should compute distance as 1-score."""
    node = Node(id="n1", text="hello", document_id="d1", metadata={"k": "v"})
    result = node.to_retrieval_result(score=0.9)

    assert result["id"] == "n1"
    assert result["document"] == "hello"
    assert abs(result["distance"] - 0.1) < 1e-6


def test_node_to_retrieval_result_from_extra():
    """to_retrieval_result without score should fall back to extra['distance']."""
    node = Node(id="n2", text="world", document_id="d1", extra={"distance": 0.3})
    result = node.to_retrieval_result()

    assert result["distance"] == 0.3


def test_document_default_fields():
    """A bare Document() should have sensible defaults."""
    doc = Document()
    assert doc.id  # auto-generated UUID
    assert doc.text == ""
    assert doc.metadata == {}
    assert doc.extra == {}
