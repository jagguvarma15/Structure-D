"""Rich UI helpers: tables, panels, progress bars."""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()


# ── Tables ────────────────────────────────────────────────────────────────────


def render_models_table(models: list[dict[str, Any]]) -> None:
    """Render the model registry as a rich table."""
    table = Table(
        title="[bold]Model Registry[/bold]",
        title_style="cyan",
        border_style="dim",
        show_lines=False,
        pad_edge=True,
    )
    table.add_column("Alias", style="bold green", min_width=20)
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Quant", style="dim")
    table.add_column("Tasks", style="white")
    table.add_column("Context", justify="right", style="cyan")
    table.add_column("Cost/1K", justify="right", style="red")

    for m in models:
        tasks = ", ".join(t if isinstance(t, str) else t.value for t in m.get("tasks", []))
        quant = m.get("quantisation") or "—"
        table.add_row(
            m.get("alias") or m.get("name", "?"),
            f"{m.get('size_b', 0):.1f}B",
            quant,
            tasks,
            str(m.get("max_context", "?")),
            f"${m.get('cost_per_1k_tokens', 0):.3f}",
        )

    console.print()
    console.print(table)


def render_schemas_table(schemas: dict[str, type]) -> None:
    """Render built-in schemas as a rich table."""
    table = Table(
        title="[bold]Built-in Schemas[/bold]",
        title_style="cyan",
        border_style="dim",
    )
    table.add_column("Name", style="bold green", min_width=22)
    table.add_column("Description", style="white")

    for name, cls in schemas.items():
        doc = (cls.__doc__ or "").strip().split("\n")[0]
        table.add_row(name, doc)

    console.print()
    console.print(table)


def render_formats_table(formats_map: dict[str, list[str]]) -> None:
    """Render supported formats as a rich table."""
    table = Table(
        title="[bold]Supported Input Formats[/bold]",
        title_style="cyan",
        border_style="dim",
    )
    table.add_column("Format", style="bold green", min_width=20)
    table.add_column("Extensions", style="white")

    for fmt_name, exts in sorted(formats_map.items()):
        table.add_row(fmt_name, "  ".join(sorted(exts)))

    console.print()
    console.print(table)


def render_config_tree(config: dict[str, Any], title: str = "Configuration") -> None:
    """Render configuration as a rich tree."""
    tree = Tree(f"[bold cyan]{title}[/bold cyan]")
    _build_tree(tree, config)
    console.print()
    console.print(tree)


def _build_tree(tree: Tree, data: dict[str, Any] | list | Any, depth: int = 0) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                branch = tree.add(f"[bold]{key}[/bold]")
                _build_tree(branch, value, depth + 1)
            else:
                tree.add(f"[bold]{key}[/bold]: [dim]{value}[/dim]")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                branch = tree.add(f"[dim][{i}][/dim]")
                _build_tree(branch, item, depth + 1)
            else:
                tree.add(f"[dim]{item}[/dim]")


def render_extraction_results(results: list[dict[str, Any]]) -> None:
    """Render extraction results as a styled summary."""
    valid = sum(1 for r in results if r.get("is_valid"))
    total = len(results)

    # Summary panel
    color = "green" if valid == total else ("yellow" if valid > 0 else "red")
    summary = f"[bold {color}]{valid}[/bold {color}] / {total} chunks validated"
    console.print(Panel(summary, title="Results", border_style=color, padding=(0, 2)))

    # Details table
    if results:
        table = Table(border_style="dim", show_lines=True, pad_edge=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Chunk", style="cyan", max_width=12)
        table.add_column("Format", style="yellow", width=10)
        table.add_column("Valid", width=6)
        table.add_column("Latency", justify="right", width=10)
        table.add_column("Output (preview)", style="white", max_width=60)

        for i, r in enumerate(results, 1):
            is_valid = r.get("is_valid", False)
            status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
            chunk_id = (r.get("chunk_id") or "")[:10]
            fmt = r.get("source_format", "?")
            latency = f"{r.get('latency_ms', 0):.0f}ms"
            output = r.get("structured_output", {})
            preview = str(output)[:55] + "…" if len(str(output)) > 55 else str(output)
            if not is_valid:
                errors = r.get("validation_errors", [])
                preview = f"[red]{'; '.join(errors[:2])}[/red]"

            table.add_row(str(i), chunk_id, fmt, status, latency, preview)

        console.print(table)


def render_status(vllm_ok: bool, vllm_url: str, models_count: int, config_path: str) -> None:
    """Render system status panel."""
    vllm_status = "[bold green]● Connected[/bold green]" if vllm_ok else "[bold red]● Unreachable[/bold red]"

    table = Table(show_header=False, border_style="dim", pad_edge=True)
    table.add_column("Key", style="bold", min_width=18)
    table.add_column("Value")
    table.add_row("vLLM Server", f"{vllm_status}  [dim]({vllm_url})[/dim]")
    table.add_row("Models Loaded", str(models_count))
    table.add_row("Config", config_path)

    console.print()
    console.print(Panel(table, title="[bold]System Status[/bold]", border_style="cyan"))


def create_progress() -> Progress:
    """Create a rich progress bar for pipeline operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )
