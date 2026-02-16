#!/usr/bin/env python3
"""
Example: Batch extraction of multiple files (any format) with CSV output.

Usage:
    python examples/batch_extraction.py path/to/folder/ --format csv
    python examples/batch_extraction.py path/to/folder/ --schema table
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from structure_d.config import get_settings
from structure_d.monitoring.logging import setup_logging
from structure_d.pipeline import Pipeline
from structure_d.schemas.base import TaskType
from structure_d.schemas.generic import BUILTIN_SCHEMAS, GenericExtraction


async def main(folder: str, output_format: str = "jsonl", schema_name: str = "generic") -> None:
    setup_logging(log_format="console")
    settings = get_settings()

    # Resolve the schema by name
    schema_cls = BUILTIN_SCHEMAS.get(schema_name, GenericExtraction)

    pipeline = Pipeline(
        schema_cls=schema_cls,
        task=TaskType.EXTRACTION,
    )

    folder_path = Path(folder)
    files = sorted(
        f for f in folder_path.rglob("*")
        if f.is_file() and f.suffix.lower() in settings.ingestion.supported_extensions
    )

    print(f"Processing {len(files)} files from {folder}")
    print(f"Schema: {schema_name}  |  Output: {output_format}")

    all_results = await pipeline.run_many(
        files,
        save_format=output_format,
    )

    total = sum(len(v) for v in all_results.values())
    valid = sum(1 for v in all_results.values() for r in v if r.is_valid)
    print(f"\nDone: {total} chunks processed, {valid} valid extractions.")
    print(f"Output saved to: {settings.storage.output_directory}/")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/batch_extraction.py <folder> [--format csv|jsonl] [--schema generic|key_value|table|entity|form]")
        sys.exit(1)

    fmt = "jsonl"
    schema = "generic"

    if "--format" in sys.argv:
        idx = sys.argv.index("--format")
        fmt = sys.argv[idx + 1]

    if "--schema" in sys.argv:
        idx = sys.argv.index("--schema")
        schema = sys.argv[idx + 1]

    asyncio.run(main(sys.argv[1], fmt, schema))
