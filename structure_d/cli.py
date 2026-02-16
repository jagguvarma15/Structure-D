"""Command-line interface for Structure-D."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import structlog

from structure_d import __version__

logger = structlog.get_logger(__name__)


@click.group()
@click.version_option(__version__)
def main() -> None:
    """Structure-D: Convert unstructured data to structured formats."""


@main.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--task", "-t", default="extraction", help="Task: extraction, classification, summarisation, sentiment.")
@click.option("--model", "-m", default=None, help="Model name or alias (default: auto-route).")
@click.option("--parser", "-p", default=None, help="Parser name override.")
@click.option("--schema", "-s", default="generic", help="Built-in schema: generic, key_value, table, entity, classification, summary, form, document_structure. Or a dotted Python path.")
@click.option("--output-format", "-f", default="jsonl", type=click.Choice(["jsonl", "csv"]), help="Output format.")
@click.option("--output-dir", "-o", default=None, help="Output directory.")
@click.option("--config", "-c", default=None, help="Config YAML path.")
def extract(
    files: tuple[str, ...],
    task: str,
    model: str | None,
    parser: str | None,
    schema: str,
    output_format: str,
    output_dir: str | None,
    config: str | None,
) -> None:
    """Extract structured data from one or more files of any format."""
    from structure_d.monitoring.logging import setup_logging
    from structure_d.pipeline import Pipeline
    from structure_d.schemas.base import TaskType

    setup_logging(log_format="console")

    schema_cls = _resolve_schema(schema)

    pipeline = Pipeline(
        schema_cls=schema_cls,
        task=TaskType(task),
        config_path=config,
    )

    if output_dir:
        pipeline.jsonl_writer.output_dir = Path(output_dir)
        pipeline.csv_writer.output_dir = Path(output_dir)

    async def _run() -> None:
        for fpath in files:
            fp = Path(fpath)
            click.echo(f"Processing: {fp.name}  (format: {fp.suffix})")
            results = await pipeline.run(
                fp,
                parser_name=parser,
                model=model,
                save_format=output_format,
            )
            valid = sum(1 for r in results if r.is_valid)
            click.echo(f"  ✓ {valid}/{len(results)} chunks valid")

    asyncio.run(_run())


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host.")
@click.option("--port", default=8080, help="Bind port.")
@click.option("--workers", default=4, help="Number of workers.")
@click.option("--config", "-c", default=None, help="Config YAML path.")
def serve(host: str, port: int, workers: int, config: str | None) -> None:
    """Start the Structure-D API server."""
    try:
        import uvicorn
    except ImportError:
        click.echo("uvicorn is required. Install with: pip install structure-d[api]")
        sys.exit(1)

    if config:
        import os

        os.environ["SD_CONFIG_PATH"] = config

    uvicorn.run(
        "structure_d.api.app:create_app",
        host=host,
        port=port,
        workers=workers,
        factory=True,
    )


@main.command()
def models() -> None:
    """List available models from the registry."""
    from structure_d.config import get_settings
    from structure_d.models.registry import ModelRegistry

    settings = get_settings()
    registry = ModelRegistry.from_yaml(settings.models.registry_path)

    for entry in registry.list_models():
        tasks = ", ".join(t.value for t in entry.tasks)
        quant = f" ({entry.quantisation})" if entry.quantisation else ""
        click.echo(
            f"  {entry.alias or entry.name:30s}  "
            f"{entry.size_b:5.1f}B{quant:8s}  "
            f"tasks=[{tasks}]  "
            f"ctx={entry.max_context}"
        )


@main.command()
def schemas() -> None:
    """List available built-in extraction schemas."""
    from structure_d.schemas.generic import BUILTIN_SCHEMAS

    click.echo("Built-in schemas:")
    for name, cls in BUILTIN_SCHEMAS.items():
        doc = (cls.__doc__ or "").strip().split("\n")[0]
        click.echo(f"  {name:25s}  {doc}")


@main.command()
def formats() -> None:
    """List supported input file formats."""
    from structure_d.schemas.base import _EXT_TO_FORMAT

    click.echo("Supported file formats:")
    by_format: dict[str, list[str]] = {}
    for ext, fmt in _EXT_TO_FORMAT.items():
        by_format.setdefault(fmt.value, []).append(ext)
    for fmt_name, exts in sorted(by_format.items()):
        click.echo(f"  {fmt_name:20s}  {', '.join(sorted(exts))}")


def _resolve_schema(name_or_path: str):  # noqa: ANN201
    """
    Resolve a schema from either a built-in name or a dotted Python path.

    Built-in names: generic, key_value, table, entity, classification,
    summary, form, document_structure.
    """
    from structure_d.schemas.generic import BUILTIN_SCHEMAS

    # Check built-in schemas first
    if name_or_path in BUILTIN_SCHEMAS:
        return BUILTIN_SCHEMAS[name_or_path]

    # Try as a dotted Python path (e.g. "mypackage.schemas.MyModel")
    if "." in name_or_path:
        parts = name_or_path.rsplit(".", 1)
        if len(parts) == 2:
            import importlib

            mod = importlib.import_module(parts[0])
            return getattr(mod, parts[1])

    click.echo(
        f"Unknown schema: {name_or_path!r}. "
        f"Available built-in: {sorted(BUILTIN_SCHEMAS.keys())}"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
