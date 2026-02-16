"""
Generic extraction schemas — format-aware, domain-agnostic.

These schemas work with *any* document type.  Users define the fields they
need via JSON Schema or Pydantic models at runtime; the schemas here provide
sensible defaults and building blocks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Fully open schema (accepts any JSON) ──────────────────────────────────────


class GenericExtraction(BaseModel):
    """
    A permissive schema that accepts **any** key-value output from the LLM.

    Use this when you don't know the fields ahead of time and want the model
    to decide what to extract.
    """

    model_config = {"extra": "allow"}


# ── Key-value extraction ──────────────────────────────────────────────────────


class KeyValuePair(BaseModel):
    """A single extracted key-value pair."""

    key: str = Field(description="Field name / label")
    value: str | None = Field(default=None, description="Extracted value")
    confidence: float | None = Field(default=None, description="Confidence score 0–1")
    page: int | None = Field(default=None, description="Source page number (if applicable)")


class KeyValueExtraction(BaseModel):
    """Extract a flat list of key-value pairs from any document."""

    pairs: list[KeyValuePair] = Field(
        default_factory=list,
        description="Extracted key-value pairs",
    )


# ── Table / tabular data ─────────────────────────────────────────────────────


class TableRow(BaseModel):
    """One row of a table as a string-keyed dict."""

    cells: dict[str, str | None] = Field(
        default_factory=dict,
        description="Column name → cell value",
    )


class TableExtraction(BaseModel):
    """Extract tabular data from spreadsheets, PDFs with tables, or HTML."""

    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[TableRow] = Field(default_factory=list, description="Table rows")


# ── Entity extraction ─────────────────────────────────────────────────────────


class Entity(BaseModel):
    """A named entity extracted from text."""

    text: str = Field(description="The entity surface form")
    label: str = Field(description="Entity type (e.g. PERSON, ORG, DATE, AMOUNT)")
    start: int | None = Field(default=None, description="Character offset start")
    end: int | None = Field(default=None, description="Character offset end")


class EntityExtraction(BaseModel):
    """Extract named entities from any document format."""

    entities: list[Entity] = Field(default_factory=list, description="Extracted entities")


# ── Classification ────────────────────────────────────────────────────────────


class ClassificationResult(BaseModel):
    """Classify a document or chunk into one or more categories."""

    label: str = Field(description="Predicted category / class")
    confidence: float | None = Field(default=None, description="Confidence score 0–1")
    labels: list[str] = Field(
        default_factory=list,
        description="All candidate labels (multi-label)",
    )
    scores: list[float] = Field(
        default_factory=list,
        description="Scores for each candidate label",
    )


# ── Summarisation ─────────────────────────────────────────────────────────────


class SummaryResult(BaseModel):
    """Summarise a document or chunk."""

    summary: str = Field(default="", description="Generated summary")
    bullet_points: list[str] = Field(
        default_factory=list,
        description="Key points as bullet items",
    )


# ── Form / structured document fields ────────────────────────────────────────


class FormField(BaseModel):
    """A single field extracted from a form (scanned or digital)."""

    field_name: str = Field(description="Label / question text")
    field_value: str | None = Field(default=None, description="Filled-in value")
    field_type: str | None = Field(
        default=None,
        description="Data type hint (text, number, date, checkbox, etc.)",
    )
    bounding_box: list[float] | None = Field(
        default=None,
        description="[x1, y1, x2, y2] bounding box in normalised coords",
    )
    page: int | None = Field(default=None, description="Page number")


class FormExtraction(BaseModel):
    """Extract structured fields from a form document (any format)."""

    fields: list[FormField] = Field(default_factory=list, description="Form fields")


# ── Section / structure extraction ────────────────────────────────────────────


class Section(BaseModel):
    """A document section (heading + body)."""

    heading: str = Field(default="", description="Section heading")
    body: str = Field(default="", description="Section body text")
    level: int = Field(default=1, description="Heading depth (1 = top-level)")


class DocumentStructure(BaseModel):
    """Extract the structural outline of a document."""

    title: str | None = Field(default=None, description="Document title")
    sections: list[Section] = Field(default_factory=list, description="Document sections")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary extracted metadata",
    )


# ── Convenience registry ──────────────────────────────────────────────────────

BUILTIN_SCHEMAS: dict[str, type[BaseModel]] = {
    "generic": GenericExtraction,
    "key_value": KeyValueExtraction,
    "table": TableExtraction,
    "entity": EntityExtraction,
    "classification": ClassificationResult,
    "summary": SummaryResult,
    "form": FormExtraction,
    "document_structure": DocumentStructure,
}


def get_schema(name: str) -> type[BaseModel]:
    """
    Look up a built-in schema by name.

    Raises :class:`KeyError` if *name* is not recognised.
    """
    if name not in BUILTIN_SCHEMAS:
        raise KeyError(
            f"Unknown schema {name!r}. "
            f"Available: {sorted(BUILTIN_SCHEMAS.keys())}"
        )
    return BUILTIN_SCHEMAS[name]
