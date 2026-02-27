"""Plain text / Markdown / CSV ingestion."""

from __future__ import annotations

import asyncio
from pathlib import Path

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument


class PlainTextParser(BaseParser):
    """Parse plain text, Markdown and CSV files."""

    supported_extensions = [".txt", ".md", ".csv"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        text = file_path.read_text(encoding="utf-8", errors="replace")

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            file_size_bytes=file_path.stat().st_size,
        )

        return ParsedDocument(metadata=metadata, text=text, pages=[text])
