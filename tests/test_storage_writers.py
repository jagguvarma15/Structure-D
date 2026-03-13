"""Tests for JSONL and CSV storage writers (file I/O, no DB needed)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from structure_d.schemas.base import DocumentFormat, ExtractionResult, TaskType
from structure_d.storage.csv_store import CSVWriter
from structure_d.storage.jsonl import JSONLWriter


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_results(n: int = 3) -> list[ExtractionResult]:
    return [
        ExtractionResult(
            document_id=f"doc-{i}",
            chunk_id=f"chunk-{i}",
            source_format=DocumentFormat.PLAIN_TEXT,
            task=TaskType.EXTRACTION,
            model_used="test-model",
            raw_output=json.dumps({"key": f"val-{i}"}),
            structured_output={"key": f"val-{i}"},
            is_valid=True,
            latency_ms=10.0 * i,
            token_usage={"prompt_tokens": 5, "completion_tokens": 10},
        )
        for i in range(n)
    ]


# ── JSONL tests ──────────────────────────────────────────────────────────────


def test_jsonl_write_creates_file(tmp_path: Path):
    """JSONLWriter.write should create a .jsonl file with one line per result."""
    writer = JSONLWriter(output_dir=tmp_path)
    results = _make_results(3)
    path = writer.write(results, "out.jsonl")

    assert path.exists()
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 3


def test_jsonl_lines_are_valid_json(tmp_path: Path):
    """Each line in the JSONL output should be parseable JSON."""
    writer = JSONLWriter(output_dir=tmp_path)
    path = writer.write(_make_results(2), "out.jsonl")

    for line in path.read_text().strip().splitlines():
        data = json.loads(line)
        assert "result_id" in data
        assert "structured_output" in data
        assert data["is_valid"] is True


def test_jsonl_appends_on_second_call(tmp_path: Path):
    """Calling write twice should append (not overwrite)."""
    writer = JSONLWriter(output_dir=tmp_path)
    writer.write(_make_results(2), "out.jsonl")
    writer.write(_make_results(1), "out.jsonl")

    lines = (tmp_path / "out.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3


def test_jsonl_write_dicts(tmp_path: Path):
    """write_dicts should accept raw dicts and produce valid JSONL."""
    writer = JSONLWriter(output_dir=tmp_path)
    records = [{"a": 1}, {"b": 2}]
    path = writer.write_dicts(records, "raw.jsonl")

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}


# ── CSV tests ────────────────────────────────────────────────────────────────


def test_csv_write_creates_file(tmp_path: Path):
    """CSVWriter.write should create a CSV file with a header + data rows."""
    writer = CSVWriter(output_dir=tmp_path)
    results = _make_results(3)
    path = writer.write(results, "out.csv")

    assert path.exists()
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 3


def test_csv_header_contains_base_columns(tmp_path: Path):
    """The CSV header should include base columns plus flattened output keys."""
    writer = CSVWriter(output_dir=tmp_path)
    path = writer.write(_make_results(1), "out.csv")

    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader)
    for col in ("result_id", "document_id", "is_valid", "model_used"):
        assert col in header
    assert "key" in header  # flattened from structured_output


def test_csv_empty_results(tmp_path: Path):
    """An empty result list should return the path without crashing."""
    writer = CSVWriter(output_dir=tmp_path)
    path = writer.write([], "empty.csv")
    assert path == tmp_path / "empty.csv"


def test_csv_nested_output_flattened(tmp_path: Path):
    """Nested structured_output dicts should be dot-separated in the CSV."""
    r = ExtractionResult(
        structured_output={"person": {"name": "Alice", "age": 30}},
        is_valid=True,
    )
    writer = CSVWriter(output_dir=tmp_path)
    path = writer.write([r], "nested.csv")

    with open(path) as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["person.name"] == "Alice"
    assert row["person.age"] == "30"
