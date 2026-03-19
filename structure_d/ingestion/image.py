"""Image parsing via OCR (Tesseract / EasyOCR)."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)

IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"]


class TesseractImageParser(BaseParser):
    """Extract text from images using pytesseract."""

    supported_extensions = IMAGE_EXTENSIONS

    def __init__(self, languages: list[str] | None = None) -> None:
        self.languages = languages or ["eng"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        import pytesseract
        from PIL import Image

        img = Image.open(file_path)
        lang_str = "+".join(self.languages)
        text = pytesseract.image_to_string(img, lang=lang_str)

        # Encode image as base64 for downstream multimodal models
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            file_size_bytes=file_path.stat().st_size,
            page_count=1,
        )

        return ParsedDocument(
            metadata=metadata,
            text=text,
            pages=[text],
            images=[b64],
        )


