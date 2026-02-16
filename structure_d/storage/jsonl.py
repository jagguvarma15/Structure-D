"""JSONL output writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.schemas.base import ExtractionResult

logger = structlog.get_logger(__name__)


class JSONLWriter:
    """Write extraction results to JSONL files."""

    def __init__(self, output_dir: str | Path | None = None, indent: int | None = None) -> None:
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.storage.output_directory)
        self.indent = indent if indent is not None else settings.storage.jsonl.indent
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, results: list[ExtractionResult], filename: str = "output.jsonl") -> Path:
        """Write *results* to a JSONL file and return the path."""
        path = self.output_dir / filename
        with open(path, "a", encoding="utf-8") as f:
            for result in results:
                line = self._serialise(result)
                f.write(line + "\n")
        logger.info("jsonl_written", path=str(path), count=len(results))
        return path

    def write_dicts(self, records: list[dict[str, Any]], filename: str = "output.jsonl") -> Path:
        """Write raw dicts to JSONL."""
        path = self.output_dir / filename
        with open(path, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, default=str, indent=self.indent) + "\n")
        return path

    def _serialise(self, result: ExtractionResult) -> str:
        data = {
            "result_id": result.result_id,
            "document_id": result.document_id,
            "chunk_id": result.chunk_id,
            "source_format": result.source_format.value,
            "task": result.task.value,
            "model_used": result.model_used,
            "is_valid": result.is_valid,
            "structured_output": result.structured_output,
            "validation_errors": result.validation_errors,
            "latency_ms": result.latency_ms,
            "token_usage": result.token_usage,
            "created_at": result.created_at.isoformat(),
        }
        return json.dumps(data, default=str, indent=self.indent)


def save_as_jsonl(results: list[ExtractionResult], filename: str = "output.jsonl") -> Path:
    """Convenience function."""
    return JSONLWriter().write(results, filename)
