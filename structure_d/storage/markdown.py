"""Markdown output writer — human-readable structure, not fenced JSON."""

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

    Structured fields are rendered as headings, lists, and tables — not `` ```json``` `` blocks.
    Results are **appended** to the file, matching :class:`~structure_d.storage.jsonl.JSONLWriter`.
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

        # ── Structured output (no ```json) ───────────────────────────────────
        lines.append("### Extracted data\n")
        so = result.structured_output
        if so is None or (isinstance(so, dict) and not so) or (isinstance(so, list) and not so):
            lines.append("_No structured output._\n")
        else:
            lines.append(_structured_to_markdown(so, depth=0).rstrip())
            lines.append("\n")

        # ── Validation ────────────────────────────────────────────────────────
        lines.append("\n### Validation\n")
        if result.validation_errors:
            for err in result.validation_errors:
                lines.append(f"- {err}")
        else:
            lines.append("No errors.")
        lines.append("\n")

        return "\n".join(lines)


def _structured_to_markdown(data: Any, depth: int = 0) -> str:
    """Turn dict/list/scalars into Markdown (headings, lists, tables)."""
    if data is None:
        return "—"
    if isinstance(data, bool):
        return "true" if data else "false"
    if isinstance(data, (int, float)):
        return str(data)
    if isinstance(data, str):
        return data.strip() or "—"
    if isinstance(data, list):
        if not data:
            return "_Empty._\n"
        if all(isinstance(x, dict) for x in data):
            return _objects_to_markdown_table(data)
        parts: list[str] = []
        for item in data:
            block = _structured_to_markdown(item, depth + 1).rstrip()
            if "\n" in block:
                parts.append("- \n" + "\n".join(f"  {ln}" for ln in block.splitlines()))
            else:
                parts.append(f"- {block}")
        return "\n".join(parts) + "\n"
    if isinstance(data, dict):
        if not data:
            return "_Empty._\n"
        chunks: list[str] = []
        for k, v in data.items():
            h = min(3 + depth, 6)
            k_safe = str(k).replace("\n", " ")
            if isinstance(v, dict) and v:
                chunks.append(f"\n{'#' * h} {k_safe}\n")
                chunks.append(_structured_to_markdown(v, depth + 1))
            elif isinstance(v, list):
                if v and all(isinstance(x, dict) for x in v):
                    chunks.append(f"\n**{k_safe}**\n")
                    chunks.append(_objects_to_markdown_table(v))
                else:
                    chunks.append(f"\n**{k_safe}**\n")
                    chunks.append(_structured_to_markdown(v, depth + 1))
            else:
                chunks.append(f"- **{k_safe}**: {_scalar_for_list(v)}\n")
        return "".join(chunks)
    return json.dumps(data, default=str)


def _scalar_for_list(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, str):
        return v.replace("\n", "  \n")
    if isinstance(v, (dict, list)):
        if not v:
            return "_Empty._"
        return json.dumps(v, default=str)
    return str(v)


def _objects_to_markdown_table(rows: list[dict]) -> str:
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    if not keys:
        return ""
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    for r in rows:
        cells: list[str] = []
        for k in keys:
            cell = r.get(k)
            if cell is None:
                s = "—"
            elif isinstance(cell, (dict, list)):
                s = json.dumps(cell, default=str) if cell else "—"
            else:
                s = str(cell)
            cells.append(s.replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
