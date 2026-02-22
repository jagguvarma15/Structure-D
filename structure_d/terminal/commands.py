"""Command handlers for the interactive terminal."""

from __future__ import annotations

import asyncio
import shlex
import time
from pathlib import Path
from typing import Any

from rich.console import Console

from structure_d.terminal.ui import (
    console,
    create_progress,
    render_config_tree,
    render_extraction_results,
    render_formats_table,
    render_models_table,
    render_schemas_table,
    render_status,
)

# ── Command registry ──────────────────────────────────────────────────────────


async def cmd_extract(args: list[str]) -> None:
    """Handle the `extract <file>` command."""
    if not args:
        console.print("[red]Usage:[/red] extract <file> [--schema name] [--task type] [--model name] [--format jsonl|csv]")
        return

    file_path = args[0]
    fp = Path(file_path)
    if not fp.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        return

    # Parse flags
    schema_name = _get_flag(args, "--schema", "generic")
    task = _get_flag(args, "--task", "extraction")
    model = _get_flag(args, "--model", None)
    output_format = _get_flag(args, "--format", "jsonl")
    output_dir = _get_flag(args, "--output", None)

    from structure_d.pipeline import Pipeline
    from structure_d.schemas.base import TaskType, detect_format
    from structure_d.schemas.generic import BUILTIN_SCHEMAS, GenericExtraction

    schema_cls = BUILTIN_SCHEMAS.get(schema_name, GenericExtraction)
    detected = detect_format(fp.suffix.lower())

    console.print()
    console.print(f"[bold]File:[/bold]    {fp.name}")
    console.print(f"[bold]Format:[/bold]  {detected.value}")
    console.print(f"[bold]Schema:[/bold]  {schema_name}")
    console.print(f"[bold]Task:[/bold]    {task}")
    console.print()

    pipeline = Pipeline(schema_cls=schema_cls, task=TaskType(task))

    if output_dir:
        pipeline.jsonl_writer.output_dir = Path(output_dir)
        pipeline.csv_writer.output_dir = Path(output_dir)

    with create_progress() as progress:
        ptask = progress.add_task("Extracting...", total=None)
        t0 = time.monotonic()
        results = await pipeline.run(
            fp,
            model=model,
            save_format=output_format,
        )
        elapsed = time.monotonic() - t0
        progress.update(ptask, completed=1, total=1)

    console.print(f"\n[dim]Completed in {elapsed:.1f}s[/dim]")

    render_extraction_results([
        {
            "chunk_id": r.chunk_id,
            "source_format": r.source_format.value,
            "is_valid": r.is_valid,
            "latency_ms": r.latency_ms,
            "structured_output": r.structured_output,
            "validation_errors": r.validation_errors,
        }
        for r in results
    ])


async def cmd_batch(args: list[str]) -> None:
    """Handle the `batch <directory>` command."""
    if not args:
        console.print("[red]Usage:[/red] batch <directory> [--schema name] [--format jsonl|csv]")
        return

    dir_path = Path(args[0])
    if not dir_path.is_dir():
        console.print(f"[red]Not a directory:[/red] {args[0]}")
        return

    schema_name = _get_flag(args, "--schema", "generic")
    output_format = _get_flag(args, "--format", "jsonl")

    from structure_d.config import get_settings
    from structure_d.pipeline import Pipeline
    from structure_d.schemas.base import TaskType
    from structure_d.schemas.generic import BUILTIN_SCHEMAS, GenericExtraction

    settings = get_settings()
    schema_cls = BUILTIN_SCHEMAS.get(schema_name, GenericExtraction)

    files = sorted(
        f for f in dir_path.rglob("*")
        if f.is_file() and f.suffix.lower() in settings.ingestion.supported_extensions
    )

    if not files:
        console.print("[yellow]No supported files found in directory.[/yellow]")
        return

    console.print(f"\n[bold]Directory:[/bold]  {dir_path}")
    console.print(f"[bold]Files:[/bold]      {len(files)}")
    console.print(f"[bold]Schema:[/bold]     {schema_name}")
    console.print()

    pipeline = Pipeline(schema_cls=schema_cls, task=TaskType.EXTRACTION)
    all_results: list[dict[str, Any]] = []

    with create_progress() as progress:
        ptask = progress.add_task("Processing files...", total=len(files))
        for fp in files:
            results = await pipeline.run(fp, save_format=output_format)
            for r in results:
                all_results.append({
                    "chunk_id": r.chunk_id,
                    "source_format": r.source_format.value,
                    "is_valid": r.is_valid,
                    "latency_ms": r.latency_ms,
                    "structured_output": r.structured_output,
                    "validation_errors": r.validation_errors,
                })
            progress.advance(ptask)

    render_extraction_results(all_results)


def cmd_models() -> None:
    """Handle the `models` command."""
    from structure_d.config import get_settings
    from structure_d.models.registry import ModelRegistry

    settings = get_settings()
    registry = ModelRegistry.from_yaml(settings.models.registry_path)
    models = [m.model_dump() for m in registry.list_models()]
    render_models_table(models)


def cmd_schemas() -> None:
    """Handle the `schemas` command."""
    from structure_d.schemas.generic import BUILTIN_SCHEMAS

    render_schemas_table(BUILTIN_SCHEMAS)


def cmd_formats() -> None:
    """Handle the `formats` command."""
    from structure_d.schemas.base import _EXT_TO_FORMAT

    by_format: dict[str, list[str]] = {}
    for ext, fmt in _EXT_TO_FORMAT.items():
        by_format.setdefault(fmt.value, []).append(ext)
    render_formats_table(by_format)


def cmd_config() -> None:
    """Handle the `config` command."""
    from structure_d.config import get_settings

    settings = get_settings()
    # Convert to a clean dict for display
    data = settings.model_dump()
    render_config_tree(data)


async def cmd_status() -> None:
    """Handle the `status` command — check vLLM connectivity."""
    from structure_d.config import get_settings
    from structure_d.models.registry import ModelRegistry

    settings = get_settings()
    vllm_url = settings.inference.provider.vllm.api_base
    config_path = "configs/default.yaml"

    # Check vLLM
    vllm_ok = False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{vllm_url}/models")
            vllm_ok = resp.status_code == 200
    except Exception:
        vllm_ok = False

    # Count models
    registry = ModelRegistry.from_yaml(settings.models.registry_path)
    models_count = len(registry.list_models())

    render_status(vllm_ok, vllm_url, models_count, config_path)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_flag(args: list[str], flag: str, default: str | None) -> str | None:
    """Extract a --flag value from an args list."""
    try:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    except ValueError:
        pass
    return default
