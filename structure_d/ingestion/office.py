"""Office document parsing (DOCX, XLSX, PPTX)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)


class DocxParser(BaseParser):
    """Parse .docx files using python-docx."""

    supported_extensions = [".docx"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        from docx import Document

        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs)

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=".docx",
            file_size_bytes=file_path.stat().st_size,
        )

        return ParsedDocument(metadata=metadata, text=text, pages=[text])


class XlsxParser(BaseParser):
    """Parse .xlsx files using openpyxl."""

    supported_extensions = [".xlsx"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        from openpyxl import load_workbook

        wb = load_workbook(str(file_path), read_only=True, data_only=True)
        pages: list[str] = []
        tables: list[dict[str, Any]] = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else "" for c in row])
            tables.append({"sheet": sheet_name, "data": rows})
            page_text = "\n".join(["\t".join(r) for r in rows])
            pages.append(page_text)

        wb.close()
        text = "\n\n".join(pages)

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=".xlsx",
            file_size_bytes=file_path.stat().st_size,
            page_count=len(pages),
        )

        return ParsedDocument(metadata=metadata, text=text, pages=pages, tables=tables)


class PptxParser(BaseParser):
    """Parse .pptx files using python-pptx."""

    supported_extensions = [".pptx"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        from pptx import Presentation

        prs = Presentation(str(file_path))
        pages: list[str] = []

        for slide in prs.slides:
            parts: list[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    parts.append(shape.text_frame.text)
            pages.append("\n".join(parts))

        text = "\n\n".join(pages)

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=".pptx",
            file_size_bytes=file_path.stat().st_size,
            page_count=len(pages),
        )

        return ParsedDocument(metadata=metadata, text=text, pages=pages)
