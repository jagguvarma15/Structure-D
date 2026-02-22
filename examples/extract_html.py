#!/usr/bin/env python3
"""
Example: Extract entities from an HTML page.

Usage:
    python examples/extract_html.py path/to/page.html
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure_d.monitoring.logging import setup_logging
from structure_d.pipeline import Pipeline
from structure_d.schemas.base import TaskType
from structure_d.schemas.generic import EntityExtraction


async def main(file_path: str) -> None:
    setup_logging(log_format="console")

    pipeline = Pipeline(
        schema_cls=EntityExtraction,
        task=TaskType.EXTRACTION,
    )

    results = await pipeline.run(
        Path(file_path),
        save_format="jsonl",
        output_filename="html_entity_extraction",
    )

    print("\n" + "=" * 60)
    print("HTML → ENTITY EXTRACTION")
    print("=" * 60)

    for r in results:
        status = "✓ VALID" if r.is_valid else "✗ INVALID"
        print(f"\n[{status}] Chunk: {r.chunk_id} | Format: {r.source_format.value}")
        if r.is_valid and isinstance(r.structured_output, dict):
            for ent in r.structured_output.get("entities", []):
                # ent may be a dict (from JSON) or an Entity-like object
                label = ent.get("label", "?") if isinstance(ent, dict) else getattr(ent, "label", "?")
                text = ent.get("text", "") if isinstance(ent, dict) else getattr(ent, "text", "")
                print(f"    [{label}] {text}")
        else:
            print(f"  Errors: {r.validation_errors}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/extract_html.py <page.html>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
