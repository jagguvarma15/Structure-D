#!/usr/bin/env python3
"""
Example: Extract structured key-value data from a PDF.

Usage:
    python examples/extract_pdf.py path/to/document.pdf

Requires a running vLLM server (see docker-compose.yml).
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
from structure_d.schemas.generic import KeyValueExtraction


async def main(file_path: str) -> None:
    setup_logging(log_format="console")

    pipeline = Pipeline(
        schema_cls=KeyValueExtraction,
        task=TaskType.EXTRACTION,
    )

    results = await pipeline.run(
        Path(file_path),
        save_format="jsonl",
        output_filename="pdf_extraction",
    )

    print("\n" + "=" * 60)
    print("PDF KEY-VALUE EXTRACTION")
    print("=" * 60)

    for r in results:
        status = "✓ VALID" if r.is_valid else "✗ INVALID"
        print(f"\n[{status}] Chunk: {r.chunk_id}")
        print(f"  Format: {r.source_format.value}")
        print(f"  Model: {r.model_used}")
        print(f"  Latency: {r.latency_ms:.0f}ms")
        if r.is_valid:
            print(f"  Output: {json.dumps(r.structured_output, indent=2)}")
        else:
            print(f"  Errors: {r.validation_errors}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/extract_pdf.py <document.pdf>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
