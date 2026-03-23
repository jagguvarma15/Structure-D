"""Parquet output writer (columnar, same flattening as CSV)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.schemas.base import ExtractionResult

logger = structlog.get_logger(__name__)


class ParquetWriter:
    """Write extraction results to Parquet (requires ``pyarrow``)."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.storage.output_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, results: list[ExtractionResult], filename: str = "output.parquet") -> Path:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as e:  # pragma: no cover - optional dependency
            raise ImportError(
                "Parquet output requires pyarrow. Install with: pip install 'structure-d[parquet]'"
            ) from e

        if not results:
            path = self.output_dir / filename
            return path

        all_fields: dict[str, None] = {}
        rows: list[dict[str, Any]] = []
        for r in results:
            base = {
                "result_id": str(r.result_id),
                "document_id": str(r.document_id),
                "chunk_id": r.chunk_id or "",
                "source_format": r.source_format.value,
                "task": r.task.value,
                "model_used": r.model_used or "",
                "is_valid": r.is_valid,
                "latency_ms": r.latency_ms,
            }
            flat = self._flatten(r.structured_output)
            base.update(flat)
            for key in flat:
                all_fields[key] = None
            rows.append(base)

        fieldnames = [
            "result_id",
            "document_id",
            "chunk_id",
            "source_format",
            "task",
            "model_used",
            "is_valid",
            "latency_ms",
        ] + list(all_fields.keys())

        # Normalise row keys so pyarrow sees a stable schema
        table_rows = [{k: row.get(k) for k in fieldnames} for row in rows]
        table = pa.Table.from_pylist(table_rows)

        path = self.output_dir / filename
        pq.write_table(table, path, compression="zstd")
        logger.info("parquet_written", path=str(path), count=len(results))
        return path

    @staticmethod
    def _flatten(data: dict[str, Any] | list[Any] | None, prefix: str = "") -> dict[str, Any]:
        """Flatten nested dicts into dot-separated keys (same rules as CSV)."""
        items: dict[str, Any] = {}
        if data is None:
            return items
        if isinstance(data, dict):
            for k, v in data.items():
                key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
                if isinstance(v, dict):
                    items.update(ParquetWriter._flatten(v, key))
                elif isinstance(v, list):
                    items[key] = json.dumps(v, default=str)
                else:
                    items[key] = v
        elif isinstance(data, list):
            items[prefix or "data"] = json.dumps(data, default=str)
        return items
