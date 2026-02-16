"""PDF parsing using PyMuPDF, pdfplumber and OCR fallback."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)


class PyMuPDFParser(BaseParser):
    """Extract text and metadata from PDFs using PyMuPDF (fitz)."""

    supported_extensions = [".pdf"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        import fitz  # PyMuPDF

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        import fitz

        doc = fitz.open(str(file_path))
        pages: list[str] = []
        full_text_parts: list[str] = []

        for page in doc:
            text = page.get_text("text")
            pages.append(text)
            full_text_parts.append(text)

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            file_size_bytes=file_path.stat().st_size,
            page_count=len(doc),
        )
        doc.close()

        return ParsedDocument(
            metadata=metadata,
            text="\n\n".join(full_text_parts),
            pages=pages,
        )


class PDFPlumberParser(BaseParser):
    """Extract text and tables from PDFs using pdfplumber."""

    supported_extensions = [".pdf"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        import pdfplumber

        pages: list[str] = []
        tables: list[dict[str, Any]] = []

        with pdfplumber.open(str(file_path)) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(text)

                for table in page.extract_tables():
                    tables.append({"page": i + 1, "data": table})

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            file_size_bytes=file_path.stat().st_size,
            page_count=page_count,
        )

        return ParsedDocument(
            metadata=metadata,
            text="\n\n".join(pages),
            pages=pages,
            tables=tables,
        )


class OCRPDFParser(BaseParser):
    """
    Fallback PDF parser that rasterises pages and runs OCR.

    Requires: pdf2image, pytesseract, Tesseract system binary.
    """

    supported_extensions = [".pdf"]

    def __init__(self, languages: list[str] | None = None, dpi: int = 300) -> None:
        self.languages = languages or ["eng"]
        self.dpi = dpi

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(str(file_path), dpi=self.dpi)
        pages: list[str] = []
        lang_str = "+".join(self.languages)

        for img in images:
            text = pytesseract.image_to_string(img, lang=lang_str)
            pages.append(text)

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            file_size_bytes=file_path.stat().st_size,
            page_count=len(images),
        )

        return ParsedDocument(
            metadata=metadata,
            text="\n\n".join(pages),
            pages=pages,
        )
