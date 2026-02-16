"""Tests for generic schemas and schema registry."""

import json

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
from structure_d.schemas.base import DocumentFormat, detect_format


# ── Schema JSON generation ────────────────────────────────────────────────────


def test_key_value_schema_json():
    schema = KeyValueExtraction.model_json_schema()
    raw = json.dumps(schema)
    assert "pairs" in raw
    assert "key" in raw
    assert "value" in raw


def test_table_schema_json():
    schema = TableExtraction.model_json_schema()
    raw = json.dumps(schema)
    assert "headers" in raw
    assert "rows" in raw


def test_entity_schema_json():
    schema = EntityExtraction.model_json_schema()
    raw = json.dumps(schema)
    assert "entities" in raw
    assert "label" in raw


def test_form_schema_json():
    schema = FormExtraction.model_json_schema()
    raw = json.dumps(schema)
    assert "fields" in raw
    assert "field_name" in raw


def test_classification_schema_json():
    schema = ClassificationResult.model_json_schema()
    raw = json.dumps(schema)
    assert "label" in raw
    assert "confidence" in raw


def test_summary_schema_json():
    schema = SummaryResult.model_json_schema()
    raw = json.dumps(schema)
    assert "summary" in raw
    assert "bullet_points" in raw


def test_document_structure_schema_json():
    schema = DocumentStructure.model_json_schema()
    raw = json.dumps(schema)
    assert "title" in raw
    assert "sections" in raw


# ── Schema instantiation ─────────────────────────────────────────────────────


def test_generic_extraction_accepts_any_field():
    obj = GenericExtraction(foo="bar", count=42)
    dumped = obj.model_dump()
    assert dumped["foo"] == "bar"
    assert dumped["count"] == 42


def test_key_value_extraction_instantiation():
    obj = KeyValueExtraction(pairs=[
        {"key": "name", "value": "Alice"},
        {"key": "age", "value": "30", "confidence": 0.95},
    ])
    assert len(obj.pairs) == 2
    assert obj.pairs[0].key == "name"


def test_table_extraction_instantiation():
    obj = TableExtraction(
        headers=["col1", "col2"],
        rows=[{"cells": {"col1": "a", "col2": "b"}}],
    )
    assert len(obj.headers) == 2
    assert len(obj.rows) == 1


# ── Schema registry ──────────────────────────────────────────────────────────


def test_builtin_schemas_has_expected_keys():
    expected = {"generic", "key_value", "table", "entity", "classification", "summary", "form", "document_structure"}
    assert expected == set(BUILTIN_SCHEMAS.keys())


def test_get_schema_by_name():
    cls = get_schema("key_value")
    assert cls is KeyValueExtraction


def test_get_schema_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_schema("nonexistent_schema")


# ── Format detection ─────────────────────────────────────────────────────────


def test_detect_pdf_format():
    assert detect_format(".pdf") == DocumentFormat.PDF


def test_detect_image_formats():
    for ext in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
        assert detect_format(ext) == DocumentFormat.IMAGE


def test_detect_html_format():
    assert detect_format(".html") == DocumentFormat.HTML
    assert detect_format(".htm") == DocumentFormat.HTML


def test_detect_office_formats():
    assert detect_format(".docx") == DocumentFormat.DOCX
    assert detect_format(".xlsx") == DocumentFormat.XLSX
    assert detect_format(".pptx") == DocumentFormat.PPTX


def test_detect_email_format():
    assert detect_format(".eml") == DocumentFormat.EMAIL


def test_detect_unknown_format():
    assert detect_format(".xyz") == DocumentFormat.UNKNOWN
