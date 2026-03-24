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
            lines.append(_render_schema_aware(so, task=result.task.value).rstrip())
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


def _render_with_layout(data: Any, *, task: str) -> tuple[str, str]:
    if _is_summary_payload(task, data):
        return "summary", _render_summary_markdown(data)
    if _is_classification_payload(task, data):
        return "classification", _render_classification_markdown(data)
    if _is_form_payload(task, data):
        return "form", _render_form_markdown(data)
    return "generic", _structured_to_markdown(data, depth=0)


def _is_summary_payload(task: str, data: Any) -> bool:
    t = task.lower()
    if "summary" in t or "summaris" in t:
        return True
    return isinstance(data, dict) and any(k in data for k in ("summary", "key_points", "bullet_points"))


def _is_classification_payload(task: str, data: Any) -> bool:
    t = task.lower()
    if "classif" in t or "sentiment" in t:
        return True
    if not isinstance(data, dict):
        return False
    return "label" in data and any(k in data for k in ("confidence", "secondary_labels", "labels", "scores"))


def _is_form_payload(task: str, data: Any) -> bool:
    t = task.lower()
    if "form" in t:
        return True
    return isinstance(data, dict) and isinstance(data.get("fields"), list)


def _render_summary_markdown(data: Any) -> str:
    if not isinstance(data, dict):
        return _structured_to_markdown(data)
    parts: list[str] = []
    title = str(data.get("title", "")).strip()
    if title:
        parts.append(f"#### {title}\n")
    summary = str(data.get("summary", "")).strip()
    if summary:
        parts.append(summary + "\n")
    points = data.get("key_points") if isinstance(data.get("key_points"), list) else data.get("bullet_points")
    if isinstance(points, list) and points:
        parts.append("**Key points**")
        parts.extend(f"- {_scalar_for_list(p)}" for p in points)
        parts.append("")
    if "word_count_estimate" in data:
        parts.append(f"_Word count estimate: {_scalar_for_list(data['word_count_estimate'])}_")
    rendered = "\n".join(parts).strip()
    return rendered + "\n" if rendered else _structured_to_markdown(data)


def _render_classification_markdown(data: Any) -> str:
    if not isinstance(data, dict):
        return _structured_to_markdown(data)
    lines: list[str] = ["| Field | Value |", "|---|---|"]
    if "label" in data:
        lines.append(f"| Label | {_table_cell(data['label'])} |")
    if "confidence" in data:
        lines.append(f"| Confidence | {_table_cell(data['confidence'])} |")
    lines.append("")

    reasoning = str(data.get("reasoning", "")).strip()
    if reasoning:
        lines.extend(["**Reasoning**", "", reasoning, ""])

    labels = data.get("labels")
    scores = data.get("scores")
    if isinstance(labels, list) and isinstance(scores, list) and labels and len(labels) == len(scores):
        lines.extend(["**Candidate labels**", "", "| Label | Score |", "|---|---|"])
        for label, score in zip(labels, scores):
            lines.append(f"| {_table_cell(label)} | {_table_cell(score)} |")
        lines.append("")

    secondary = data.get("secondary_labels")
    if isinstance(secondary, list) and secondary:
        lines.append("**Secondary labels**")
        lines.extend(f"- {_scalar_for_list(v)}" for v in secondary)
        lines.append("")

    rendered = "\n".join(lines).strip()
    return rendered + "\n" if rendered else _structured_to_markdown(data)


def _render_form_markdown(data: Any) -> str:
    if not isinstance(data, dict):
        return _structured_to_markdown(data)
    lines: list[str] = []
    form_type = str(data.get("form_type", "")).strip()
    if form_type:
        lines.append(f"**Form type:** {form_type}\n")

    fields = data.get("fields")
    if isinstance(fields, list) and fields and all(isinstance(x, dict) for x in fields):
        lines.extend([
            "| Field name | Value | Type | Page |",
            "|---|---|---|---|",
        ])
        for item in fields:
            lines.append(
                "| " + " | ".join(
                    [
                        _table_cell(item.get("field_name", "—")),
                        _table_cell(item.get("field_value", "—")),
                        _table_cell(item.get("field_type", "—")),
                        _table_cell(item.get("page", "—")),
                    ]
                ) + " |"
            )
        lines.append("")

    rendered = "\n".join(lines).strip()
    return rendered + "\n" if rendered else _structured_to_markdown(data)


def _table_cell(v: Any) -> str:
    return _scalar_for_list(v).replace("|", "\\|").replace("\n", " ")



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
