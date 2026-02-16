"""Pydantic output schemas for structured extraction."""

from structure_d.schemas.base import (
    ChunkMetadata,
    DocumentFormat,
    DocumentMetadata,
    ExtractionResult,
    ParsedDocument,
    TextChunk,
    detect_format,
)
from structure_d.schemas.generic import (
    BUILTIN_SCHEMAS,
    ClassificationResult,
    DocumentStructure,
    EntityExtraction,
    FormExtraction,
    GenericExtraction,
    KeyValueExtraction,
    SummaryResult,
    TableExtraction,
    get_schema,
)

__all__ = [
    "BUILTIN_SCHEMAS",
    "ChunkMetadata",
    "ClassificationResult",
    "DocumentFormat",
    "DocumentMetadata",
    "DocumentStructure",
    "EntityExtraction",
    "ExtractionResult",
    "FormExtraction",
    "GenericExtraction",
    "KeyValueExtraction",
    "ParsedDocument",
    "SummaryResult",
    "TableExtraction",
    "TextChunk",
    "detect_format",
    "get_schema",
]
