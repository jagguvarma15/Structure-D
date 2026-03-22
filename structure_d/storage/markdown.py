"""Markdown output writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.schemas.base import ExtractionResult

logger = structlog.get_logger(__name__)


class MarkdownWriter:
    """Write extraction results to a human-readable Markdown file.

    Each :class:`ExtractionResult` is rendered as a ``## Result N`` section
    containing a metadata summary table and a fenced JSON block for
    ``structured_output``.  Results are **appended** to the file, matching
    the append semantics of :class:`~structure_d.storage.jsonl.JSONLWriter`.
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.storage.output_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        results: list[ExtractionResult],
        filename: str = "output.md",
    ) -> Path:
        """Render *results* to a Markdown file and return the path."""
        path = self.output_dir / filename
        is_new = not path.exists() or path.stat().st_size == 0

        with open(path, "a", encoding="utf-8") as f:
            if is_new:
                f.write("# Extraction Results\n\n")

            for i, result in enumerate(results, start=1):
                f.write(self._render_result(i, result))

        logger.info("markdown_written", path=str(path), count=len(results))
        return path

    def _render_result(self, index: int, result: ExtractionResult) -> str:
        lines: list[str] = []

        lines.append(f"---\n\n## Result {index}\n")

        # ── Metadata table ────────────────────────────────────────────────────
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| result_id | `{result.result_id}` |")
        lines.append(f"| document_id | `{result.document_id}` |")
        lines.append(f"| chunk_id | `{result.chunk_id or '—'}` |")
        lines.append(f"| source_format | {result.source_format.value} |")
        lines.append(f"| task | {result.task.value} |")
        lines.append(f"| model_used | {result.model_used or '—'} |")
        lines.append(f"| is_valid | {'✓ true' if result.is_valid else '✗ false'} |")
        lines.append(f"| latency_ms | {result.latency_ms:.1f} |")
        lines.append(f"| created_at | {result.created_at.isoformat()} |")
        lines.append("")

        # ── Structured output ─────────────────────────────────────────────────
        lines.append("### Structured Output\n")
        output_json = json.dumps(result.structured_output, indent=2, default=str)
        lines.append("```json")
        lines.append(output_json)
        lines.append("```\n")

        # ── Validation ────────────────────────────────────────────────────────
        lines.append("### Validation\n")
        if result.validation_errors:
            for err in result.validation_errors:
                lines.append(f"- {err}")
        else:
            lines.append("No errors.")
        lines.append("\n")

        return "\n".join(lines)
