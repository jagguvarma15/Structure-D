"""End-to-end pipeline tests with a fake LLM provider (no network needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from structure_d.pipeline import Pipeline
from structure_d.schemas.base import DocumentFormat, TaskType
from structure_d.schemas.generic import KeyValueExtraction
from tests.conftest import FakeProvider


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_pipeline(
    tmp_path: Path,
    provider: FakeProvider | None = None,
) -> Pipeline:
    """Build a Pipeline wired to a fake provider and tmp output dir."""
    return Pipeline(
        schema_cls=KeyValueExtraction,
        task=TaskType.EXTRACTION,
        provider=provider or FakeProvider(),
        enable_rag=False,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_pipeline_run_returns_results(sample_text_file: Path, tmp_path: Path):
    """Full pipeline run on a .txt file should return validated results."""
    pipeline = _build_pipeline(tmp_path)
    results = await pipeline.run(sample_text_file)

    assert len(results) >= 1
    for r in results:
        assert r.is_valid is True
        assert r.model_used == "fake-model"
        assert r.document_id  # non-empty
        assert r.structured_output


async def test_pipeline_run_populates_source_format(sample_text_file: Path, tmp_path: Path):
    """Every result should carry the detected source format."""
    pipeline = _build_pipeline(tmp_path)
    results = await pipeline.run(sample_text_file)

    for r in results:
        assert r.source_format == DocumentFormat.PLAIN_TEXT


async def test_pipeline_run_saves_jsonl(sample_text_file: Path, tmp_path: Path):
    """Pipeline should write JSONL when save_format='jsonl'."""
    pipeline = _build_pipeline(tmp_path)
    # Redirect output to tmp_path so previous runs cannot pollute line count.
    pipeline.jsonl_writer.output_dir = tmp_path
    unique_name = f"test_out_{id(pipeline)}"
    results = await pipeline.run(
        sample_text_file, save_format="jsonl", output_filename=unique_name,
    )
    outfile = tmp_path / f"{unique_name}.jsonl"
    assert outfile.exists()
    lines = outfile.read_text().strip().splitlines()
    assert len(lines) == len(results)


async def test_pipeline_run_saves_csv(sample_text_file: Path, tmp_path: Path):
    """Pipeline should write CSV when save_format='csv'."""
    pipeline = _build_pipeline(tmp_path)
    results = await pipeline.run(
        sample_text_file, save_format="csv", output_filename="test_out",
    )
    outfile = Path(pipeline.csv_writer.output_dir / "test_out.csv")
    assert outfile.exists()


async def test_pipeline_run_many(sample_text_file: Path, sample_md_file: Path, tmp_path: Path):
    """run_many should process multiple files and return a dict keyed by filename."""
    pipeline = _build_pipeline(tmp_path)
    results = await pipeline.run_many(
        [sample_text_file, sample_md_file], max_concurrent=2,
    )
    assert set(results.keys()) == {sample_text_file.name, sample_md_file.name}
    for name, res_list in results.items():
        assert len(res_list) >= 1
