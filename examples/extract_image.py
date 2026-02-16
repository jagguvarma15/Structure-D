#!/usr/bin/env python3
"""
Example: Extract form fields from a scanned image (OCR + LLM).

Usage:
    python examples/extract_image.py path/to/scan.png

Requires Tesseract installed and a running vLLM server.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure_d.monitoring.logging import setup_logging
from structure_d.pipeline import Pipeline
from structure_d.schemas.base import TaskType
from structure_d.schemas.generic import FormExtraction


async def main(file_path: str) -> None:
    setup_logging(log_format="console")

    pipeline = Pipeline(
        schema_cls=FormExtraction,
        task=TaskType.EXTRACTION,
    )

    results = await pipeline.run(
        Path(file_path),
        save_format="jsonl",
        output_filename="image_form_extraction",
    )

    print("\n" + "=" * 60)
    print("IMAGE → FORM FIELD EXTRACTION")
    print("=" * 60)

    for r in results:
        status = "✓ VALID" if r.is_valid else "✗ INVALID"
        print(f"\n[{status}] Chunk: {r.chunk_id}")
        print(f"  Format: {r.source_format.value}")
        if r.is_valid:
            for field in r.structured_output.get("fields", []):
                print(f"    {field.get('field_name', '?')}: {field.get('field_value', 'N/A')}")
        else:
            print(f"  Errors: {r.validation_errors}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/extract_image.py <scan.png>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
