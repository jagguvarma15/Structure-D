"""Base schemas shared across the pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Supported extraction task types."""

    CLASSIFICATION = "classification"
    SENTIMENT = "sentiment"
    EXTRACTION = "extraction"
    SUMMARISATION = "summarisation"
    REASONING = "reasoning"
    MULTIMODAL = "multimodal"


class DocumentFormat(str, Enum):
    """Source document formats the framework handles."""

    PDF = "pdf"
    IMAGE = "image"
    HTML = "html"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    EMAIL = "email"
    AUDIO_TRANSCRIPT = "audio_transcript"
    PLAIN_TEXT = "plain_text"
    CSV = "csv"
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"


_EXT_TO_FORMAT: dict[str, DocumentFormat] = {
    ".pdf": DocumentFormat.PDF,
    ".png": DocumentFormat.IMAGE,
    ".jpg": DocumentFormat.IMAGE,
    ".jpeg": DocumentFormat.IMAGE,
    ".tiff": DocumentFormat.IMAGE,
    ".bmp": DocumentFormat.IMAGE,
    ".gif": DocumentFormat.IMAGE,
    ".webp": DocumentFormat.IMAGE,
    ".html": DocumentFormat.HTML,
    ".htm": DocumentFormat.HTML,
    ".docx": DocumentFormat.DOCX,
    ".xlsx": DocumentFormat.XLSX,
    ".pptx": DocumentFormat.PPTX,
    ".eml": DocumentFormat.EMAIL,
    ".srt": DocumentFormat.AUDIO_TRANSCRIPT,
    ".vtt": DocumentFormat.AUDIO_TRANSCRIPT,
    ".txt": DocumentFormat.PLAIN_TEXT,
    ".csv": DocumentFormat.CSV,
    ".md": DocumentFormat.MARKDOWN,
}


def detect_format(extension: str) -> DocumentFormat:
    """Map a file extension to a :class:`DocumentFormat`."""
    return _EXT_TO_FORMAT.get(extension.lower(), DocumentFormat.UNKNOWN)


class DocumentMetadata(BaseModel):
    """Metadata attached to every ingested document."""

    document_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    filename: str = ""
    source: str = ""  # e.g. "local", "s3://bucket/key", URL
    file_extension: str = ""
    format: DocumentFormat = DocumentFormat.UNKNOWN
    file_size_bytes: int = 0
    page_count: int | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extra: dict[str, Any] = Field(default_factory=dict)


class ChunkMetadata(BaseModel):
    """Metadata for a single text chunk produced by the chunker."""

    chunk_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    document_id: str = ""
    source_format: DocumentFormat = DocumentFormat.UNKNOWN
    page_number: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    heading: str | None = None
    token_count: int = 0


class ParsedDocument(BaseModel):
    """Output of the ingestion + parsing stage."""

    metadata: DocumentMetadata
    text: str = ""
    pages: list[str] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)  # base64 or file paths


class TextChunk(BaseModel):
    """A single chunk ready for inference."""

    text: str
    metadata: ChunkMetadata


class ExtractionResult(BaseModel):
    """Wrapper around the structured data returned by inference + validation."""

    result_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    document_id: str = ""
    chunk_id: str | None = None
    source_format: DocumentFormat = DocumentFormat.UNKNOWN
    task: TaskType = TaskType.EXTRACTION
    model_used: str = ""
    raw_output: str = ""
    structured_output: dict[str, Any] | list[Any] = Field(default_factory=dict)
    is_valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_usage: dict[str, int] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
