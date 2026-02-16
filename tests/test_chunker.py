"""Tests for the chunking module."""

from structure_d.preprocessing.chunker import Chunker


def test_fixed_chunking():
    text = "A " * 2000  # ~4000 chars = ~1000 tokens
    chunker = Chunker(strategy="fixed", max_tokens=512, overlap_tokens=64)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 512 * 4 + 100  # some tolerance


def test_sentence_chunking():
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    chunker = Chunker(strategy="sentence", max_tokens=50, overlap_tokens=10)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1
    # All text should be covered
    combined = " ".join(c.text for c in chunks)
    assert "First sentence." in combined


def test_heading_chunking():
    text = "# Heading 1\n\nParagraph one.\n\n## Heading 2\n\nParagraph two."
    chunker = Chunker(strategy="heading", max_tokens=1024, heading_level=2)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1


def test_semantic_chunking_no_headings():
    text = "Sentence one. Sentence two. Sentence three."
    chunker = Chunker(strategy="semantic", max_tokens=50, overlap_tokens=10)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 1


def test_document_id_propagation():
    text = "Some text here."
    chunker = Chunker(strategy="fixed", max_tokens=1024)
    chunks = chunker.chunk(text, document_id="doc-123")
    assert all(c.metadata.document_id == "doc-123" for c in chunks)
