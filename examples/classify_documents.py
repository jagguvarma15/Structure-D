#!/usr/bin/env python3
"""
Example: Classify documents of any format into categories.

Usage:
    python examples/classify_documents.py file1.pdf file2.html file3.docx
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure_d.monitoring.logging import setup_logging
from structure_d.pipeline import Pipeline
from structure_d.schemas.base import TaskType
from structure_d.schemas.generic import ClassificationResult


async def main(files: list[str]) -> None:
    setup_logging(log_format="console")

    pipeline = Pipeline(
        schema_cls=ClassificationResult,
        task=TaskType.CLASSIFICATION,
    )

    print("\n" + "=" * 60)
    print("DOCUMENT CLASSIFICATION")
    print("=" * 60)

    for fpath in files:
        fp = Path(fpath)
        results = await pipeline.run(fp, save_format="jsonl", output_filename="classification")

        for r in results:
            label = r.structured_output.get("label", "unknown") if r.is_valid else "ERROR"
            conf = r.structured_output.get("confidence", "?") if r.is_valid else "?"
            print(f"  {fp.name:30s}  →  {label} (confidence: {conf})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/classify_documents.py <file1> <file2> ...")
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
