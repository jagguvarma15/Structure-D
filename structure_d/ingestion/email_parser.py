"""Email (.eml) parsing."""

from __future__ import annotations

import asyncio
import email
import email.policy
from pathlib import Path

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)


class EmailParser(BaseParser):
    """Parse .eml files using the stdlib email module."""

    supported_extensions = [".eml"]

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        raw = file_path.read_bytes()
        msg = email.message_from_bytes(raw, policy=email.policy.default)

        subject = msg.get("Subject", "")
        from_addr = msg.get("From", "")
        to_addr = msg.get("To", "")
        date = msg.get("Date", "")

        # Extract body text
        body_parts: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_content()
                    if isinstance(payload, str):
                        body_parts.append(payload)
        else:
            payload = msg.get_content()
            if isinstance(payload, str):
                body_parts.append(payload)

        body = "\n".join(body_parts)
        header_block = f"From: {from_addr}\nTo: {to_addr}\nDate: {date}\nSubject: {subject}"
        full_text = f"{header_block}\n\n{body}"

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=".eml",
            file_size_bytes=file_path.stat().st_size,
            extra={
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "date": date,
            },
        )

        return ParsedDocument(metadata=metadata, text=full_text, pages=[full_text])
