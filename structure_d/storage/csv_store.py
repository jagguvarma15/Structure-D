"""CSV output writer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.schemas.base import ExtractionResult

logger = structlog.get_logger(__name__)


class CSVWriter:
    """Write extraction results to CSV files."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.storage.output_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, results: list[ExtractionResult], filename: str = "output.csv") -> Path:
        """
        Flatten structured outputs to CSV.

        Each :class:`ExtractionResult` becomes one row.  The ``structured_output``
        dict is flattened so that each key becomes a column.
        """
        if not results:
            return self.output_dir / filename

        # Collect all field names from structured outputs
        all_fields: dict[str, None] = {}
        rows: list[dict[str, Any]] = []
        for r in results:
            base = {
                "result_id": r.result_id,
                "document_id": r.document_id,
                "chunk_id": r.chunk_id,
                "source_format": r.source_format.value,
                "task": r.task.value,
                "model_used": r.model_used,
                "is_valid": r.is_valid,
                "latency_ms": r.latency_ms,
            }
            flat = self._flatten(r.structured_output)
            base.update(flat)
            for key in flat:
                all_fields[key] = None
            rows.append(base)

        fieldnames = [
            "result_id", "document_id", "chunk_id", "source_format",
            "task", "model_used", "is_valid", "latency_ms",
        ] + list(all_fields.keys())

        path = self.output_dir / filename
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        logger.info("csv_written", path=str(path), count=len(results))
        return path

    @staticmethod
    def _flatten(data: dict[str, Any] | list[Any], prefix: str = "") -> dict[str, Any]:
        """Flatten nested dicts into dot-separated keys."""
        items: dict[str, Any] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
                if isinstance(v, dict):
                    items.update(CSVWriter._flatten(v, key))
                elif isinstance(v, list):
                    items[key] = json.dumps(v, default=str)
                else:
                    items[key] = v
        elif isinstance(data, list):
            items[prefix or "data"] = json.dumps(data, default=str)
        return items
