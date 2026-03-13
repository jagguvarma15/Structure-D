"""Tests for built-in parsers that need no heavy external deps (text, HTML, email)."""

from __future__ import annotations

from pathlib import Path

import pytest

from structure_d.ingestion.email_parser import EmailParser
from structure_d.ingestion.html_parser import HTMLParser
from structure_d.ingestion.text import PlainTextParser
from structure_d.schemas.base import ParsedDocument


# ── PlainTextParser ──────────────────────────────────────────────────────────


async def test_plain_text_parse(sample_text_file: Path):
    """PlainTextParser should extract the full text of a .txt file."""
    parser = PlainTextParser()
    doc = await parser.parse(sample_text_file)

    assert isinstance(doc, ParsedDocument)
    assert "Alice" in doc.text
    assert doc.metadata.filename == "sample.txt"
    assert doc.metadata.file_extension == ".txt"
    assert doc.metadata.file_size_bytes > 0


async def test_plain_text_parse_md(sample_md_file: Path):
    """PlainTextParser should also handle .md files."""
    parser = PlainTextParser()
    doc = await parser.parse(sample_md_file)

    assert "# Title" in doc.text
    assert "Section" in doc.text


async def test_plain_text_parse_csv(sample_csv_file: Path):
    """PlainTextParser should handle .csv files as raw text."""
    parser = PlainTextParser()
    doc = await parser.parse(sample_csv_file)

    assert "name,age" in doc.text
    assert "Alice,30" in doc.text


async def test_plain_text_can_handle():
    """can_handle should return True for .txt, .md, .csv only."""
    parser = PlainTextParser()
    assert parser.can_handle(Path("a.txt")) is True
    assert parser.can_handle(Path("b.md")) is True
    assert parser.can_handle(Path("c.csv")) is True
    assert parser.can_handle(Path("d.pdf")) is False


# ── HTMLParser ───────────────────────────────────────────────────────────────


async def test_html_parse(sample_html_file: Path):
    """HTMLParser should extract visible text and strip scripts."""
    parser = HTMLParser(parser_lib="html.parser")
    doc = await parser.parse(sample_html_file)

    assert "Hello World" in doc.text
    assert "var x" not in doc.text  # script content removed
    assert doc.metadata.file_extension == ".html"
    assert doc.metadata.extra.get("title") == "Test"


async def test_html_can_handle():
    """can_handle should return True for .html and .htm."""
    parser = HTMLParser()
    assert parser.can_handle(Path("page.html")) is True
    assert parser.can_handle(Path("page.htm")) is True
    assert parser.can_handle(Path("page.txt")) is False


# ── EmailParser ──────────────────────────────────────────────────────────────


async def test_email_parse(sample_email_file: Path):
    """EmailParser should extract headers and body from a .eml file."""
    parser = EmailParser()
    doc = await parser.parse(sample_email_file)

    assert "sender@example.com" in doc.text
    assert "Test Email" in doc.text
    assert "email body" in doc.text
    assert doc.metadata.file_extension == ".eml"
    assert doc.metadata.extra["subject"] == "Test Email"


async def test_email_can_handle():
    """can_handle should return True only for .eml files."""
    parser = EmailParser()
    assert parser.can_handle(Path("msg.eml")) is True
    assert parser.can_handle(Path("msg.txt")) is False
