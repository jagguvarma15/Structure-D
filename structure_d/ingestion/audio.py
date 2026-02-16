"""Audio transcript ingestion.

This module does **not** perform speech-to-text itself (that would require
whisper / faster-whisper, which is a heavy dependency).  Instead it ingests
pre-existing transcript files (.txt, .vtt, .srt) and normalises them to
plain text.  A Whisper-based parser can be registered separately.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)

_SRT_TS = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}")
_VTT_TS = _SRT_TS  # same pattern
_SRT_INDEX = re.compile(r"^\d+$")


class TranscriptParser(BaseParser):
    """Parse plain-text, SRT or VTT transcript files."""

    supported_extensions = [".txt", ".srt", ".vtt"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        ext = file_path.suffix.lower()

        if ext in (".srt", ".vtt"):
            text = self._strip_timestamps(raw)
        else:
            text = raw

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=ext,
            file_size_bytes=file_path.stat().st_size,
        )

        return ParsedDocument(metadata=metadata, text=text.strip(), pages=[text.strip()])

    @staticmethod
    def _strip_timestamps(raw: str) -> str:
        lines: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if _SRT_TS.match(line) or _SRT_INDEX.match(line):
                continue
            if line.upper().startswith("WEBVTT"):
                continue
            lines.append(line)
        return "\n".join(lines)
