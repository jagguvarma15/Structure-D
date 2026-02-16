"""HTML / web page parsing."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)


class HTMLParser(BaseParser):
    """Parse HTML files using BeautifulSoup, extracting text and basic structure."""

    supported_extensions = [".html", ".htm"]

    def __init__(self, parser_lib: str = "lxml") -> None:
        self.parser_lib = parser_lib

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        from bs4 import BeautifulSoup

        raw = file_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw, self.parser_lib)

        # Remove script / style tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            file_size_bytes=file_path.stat().st_size,
            extra={"title": soup.title.string if soup.title else ""},
        )

        return ParsedDocument(
            metadata=metadata,
            text=text,
            pages=[text],
        )
