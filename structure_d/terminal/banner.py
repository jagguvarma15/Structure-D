"""ASCII banner and branding for the terminal UI."""

from __future__ import annotations

import os
from dataclasses import dataclass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme


# Role-based styling (easy to retheme / keep accessible)
THEME = Theme(
    {
        "frame": "white",
        "brand": "bold bright_cyan",
        "muted": "dim",
        "accent": "bright_cyan",
        "ok": "bold green",
    }
)

# Pixel wordmark with D appended (6 rows) - compact spacing
WORDMARK = [
    " ███████╗████████╗██████╗ ██╗   ██╗ ██████╗████████╗██╗   ██╗██████╗ ███████╗  ███████╗",
    " ██╔════╝╚══██╔══╝██╔══██╗██║   ██║██╔════╝╚══██╔══╝██║   ██║██╔══██╗██╔════╝  ██╔═══██╗",
    " ███████╗   ██║   ██████╔╝██║   ██║██║        ██║   ██║   ██║██████╔╝█████╗    ██║   ██║",
    " ╚════██║   ██║   ██╔══██╗██║   ██║██║        ██║   ██║   ██║██╔══██╗██╔══╝    ██║   ██║",
    " ███████║   ██║   ██║  ██║╚██████╔╝╚██████╗   ██║   ╚██████╔╝██║  ██║███████╗  ██╚═══██║",
    " ╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝  ███████╔╝",
]

TAGLINE = "Unstructured → Structured  ·  Any format, any schema, high-throughput vLLM inference"

WELCOME = """\
[bold white]Welcome to Structure-D interactive terminal.[/bold white]
Type [bold green]help[/bold green] to see available commands, or [bold green]exit[/bold green] to quit.
"""

HELP_TEXT = """\
[bold underline]Commands[/bold underline]

[bold green]extract[/bold green] <file> [options]     Extract structured data from a file
    [dim]--schema <name>    Schema: generic, key_value, table, entity, form, classification, summary, document_structure[/dim]
    [dim]--task <type>      Task: extraction, classification, summarisation, sentiment[/dim]
    [dim]--model <name>     Model name or alias (default: auto-route)[/dim]
    [dim]--format <fmt>     Output: jsonl, csv (default: jsonl)[/dim]
    [dim]--output <dir>     Output directory[/dim]

[bold green]batch[/bold green] <directory> [options]   Batch-extract from all files in a directory
    [dim]--schema <name>    Schema name (default: generic)[/dim]
    [dim]--format <fmt>     Output: jsonl, csv (default: jsonl)[/dim]

[bold green]models[/bold green]                        Show registered models
[bold green]schemas[/bold green]                       Show built-in extraction schemas
[bold green]formats[/bold green]                       Show supported input file formats
[bold green]config[/bold green]                        Show current configuration
[bold green]status[/bold green]                        Check vLLM server connectivity

[bold green]clear[/bold green]                         Clear the screen
[bold green]version[/bold green]                       Show version info
[bold green]help[/bold green]                          Show this help message
[bold green]exit[/bold green] / [bold green]quit[/bold green]                  Exit the terminal
"""


@dataclass(frozen=True)
class BrandInfo:
    version: str = "CLI v0.1.0"
    subtitle: str = "Command-line interface"


def _no_color_enabled() -> bool:
    return "NO_COLOR" in os.environ


def build_banner(console: Console, brand: BrandInfo = BrandInfo()) -> Panel:
    # Content: header + wordmark + tagline
    content = Text()
    content.append("Welcome to\n", style="muted")
    
    # Display wordmark as-is - Rich will handle overflow gracefully
    for line in WORDMARK:
        content.append(line + "\n", style="brand")
    
    content.append(brand.subtitle + "\n", style="muted")
    content.append(TAGLINE, style="muted")

    # Panel will automatically fit to terminal width
    # Rich handles overflow by wrapping or scrolling in narrow terminals
    return Panel(
        content,
        box=box.SQUARE,
        border_style="frame",
        padding=(1, 2),
        title=f"[muted]{brand.version}[/muted]",
        title_align="right",
    )


def print_banner(console: Console, brand: BrandInfo = BrandInfo()) -> None:
    if _no_color_enabled():
        console.print("Welcome to")
        for line in WORDMARK:
            console.print(line)
        console.print(TAGLINE)
        return

    console.push_theme(THEME)
    console.print(build_banner(console, brand))
    console.pop_theme()
