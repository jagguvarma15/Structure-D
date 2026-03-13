"""Tests for IngestionManager: parser resolution, error paths, multi-file ingest."""

from __future__ import annotations

from pathlib import Path

import pytest

from structure_d.exceptions import ParserError
from structure_d.ingestion.base import BaseParser, ParserRegistry
from structure_d.ingestion.manager import IngestionManager
from structure_d.ingestion.text import PlainTextParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument


# ── Helpers ──────────────────────────────────────────────────────────────────


def _tiny_registry() -> ParserRegistry:
    """Registry with only the plain-text parser registered."""
    reg = ParserRegistry()
    reg.register("plaintext", PlainTextParser())
    return reg


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_ingest_txt_file(sample_text_file: Path):
    """Ingesting a .txt file should return a populated ParsedDocument."""
    mgr = IngestionManager(registry=_tiny_registry())
    doc = await mgr.ingest(sample_text_file)

    assert isinstance(doc, ParsedDocument)
    assert "Alice" in doc.text
    assert doc.metadata.filename == "sample.txt"


async def test_ingest_unsupported_extension(tmp_path: Path):
    """Unsupported extensions should raise ParserError with context."""
    bad_file = tmp_path / "data.xyz"
    bad_file.write_text("content")

    mgr = IngestionManager(registry=_tiny_registry())
    with pytest.raises(ParserError) as exc_info:
        await mgr.ingest(bad_file)

    assert ".xyz" in str(exc_info.value)
    assert exc_info.value.file_path == str(bad_file)


async def test_ingest_unknown_parser_name(sample_text_file: Path):
    """Requesting a non-existent parser by name should raise ParserError."""
    mgr = IngestionManager(registry=_tiny_registry())
    with pytest.raises(ParserError, match="not found"):
        await mgr.ingest(sample_text_file, parser_name="nonexistent")


async def test_ingest_explicit_parser_name(sample_text_file: Path):
    """Passing a valid parser name should bypass auto-detection."""
    mgr = IngestionManager(registry=_tiny_registry())
    doc = await mgr.ingest(sample_text_file, parser_name="plaintext")
    assert "Alice" in doc.text


async def test_ingest_many_concurrent(tmp_path: Path):
    """ingest_many should process files concurrently and return all results."""
    files = []
    for i in range(5):
        f = tmp_path / f"file_{i}.txt"
        f.write_text(f"Content {i}")
        files.append(f)

    mgr = IngestionManager(registry=_tiny_registry())
    docs = await mgr.ingest_many(files, max_concurrent=3)

    assert len(docs) == 5
    texts = {d.text for d in docs}
    for i in range(5):
        assert f"Content {i}" in texts


async def test_ingest_no_parser_for_extension(tmp_path: Path):
    """When no parser handles the extension, ParserError should be raised."""
    f = tmp_path / "data.html"
    f.write_text("<html></html>")

    reg = ParserRegistry()
    reg.register("plaintext", PlainTextParser())  # only handles .txt/.md/.csv
    mgr = IngestionManager(registry=reg)

    with pytest.raises(ParserError, match="No parser registered"):
        await mgr.ingest(f)
