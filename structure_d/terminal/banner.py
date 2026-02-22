"""ASCII banner and branding for the terminal UI."""

from __future__ import annotations

import os
import shutil
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
    " ███████╗████████╗██████╗ ██╗   ██╗ ██████╗████████╗██╗   ██╗██████╗ ███████╗   ███████╗",
    " ██╔════╝╚══██╔══╝██╔══██╗██║   ██║██╔════╝╚══██╔══╝██║   ██║██╔══██╗██╔════╝   ██╔═══██╗",
    " ███████╗   ██║   ██████╔╝██║   ██║██║        ██║   ██║   ██║██████╔╝█████╗  ██ ██║   ██║",
    " ╚════██║   ██║   ██╔══██╗██║   ██║██║        ██║   ██║   ██║██╔══██╗██╔══╝     ██║   ██║",
    " ███████║   ██║   ██║  ██║╚██████╔╝╚██████╗   ██║   ╚██████╔╝██║  ██║███████╗   ██╚═══██║",
    " ╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝   ███████╔╝",
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


def _get_terminal_width(console: Console) -> int:
    """Get terminal width from console, environment variables, or system."""
    # Try console first
    if console.width and console.width > 0:
        return console.width
    
    # Try environment variable
    try:
        cols = int(os.environ.get("COLUMNS", "0"))
        if cols > 0:
            return max(60, cols)
    except (ValueError, TypeError):
        pass
    
    # Try shutil.get_terminal_size() as fallback
    try:
        size = shutil.get_terminal_size()
        if size.columns > 0:
            return max(60, size.columns)
    except (OSError, ValueError):
        pass
    
    # Default fallback
    return 120


def _get_terminal_height(console: Console) -> int:
    """Get terminal height from console, environment variables, or system."""
    # Try console first
    if console.height and console.height > 0:
        return console.height
    
    # Try environment variable
    try:
        lines = int(os.environ.get("LINES", "0"))
        if lines > 0:
            return max(10, lines)
    except (ValueError, TypeError):
        pass
    
    # Try shutil.get_terminal_size() as fallback
    try:
        size = shutil.get_terminal_size()
        if size.lines > 0:
            return max(10, size.lines)
    except (OSError, ValueError):
        pass
    
    # Default fallback
    return 30


def build_banner(console: Console, brand: BrandInfo = BrandInfo()) -> Panel:
    # Get terminal dimensions with fallback to environment variables
    terminal_width = _get_terminal_width(console)
    terminal_height = _get_terminal_height(console)
    
    # Calculate available width (account for panel borders + padding)
    # Panel borders: 2 chars, padding: 4 chars (2 on each side) = 6 total
    available_width = max(60, terminal_width - 6)
    
    # Content: header + wordmark + tagline
    content = Text()
    content.append("Welcome to\n", style="muted")
    
    # Adjust wordmark based on terminal width
    max_wordmark_width = max(len(line.rstrip()) for line in WORDMARK)
    
    if available_width >= max_wordmark_width:
        # Full wordmark fits - display as-is
        for line in WORDMARK:
            content.append(line + "\n", style="brand")
    elif available_width >= 50:
        # Medium width - truncate wordmark lines
        for line in WORDMARK:
            line_stripped = line.rstrip()
            if len(line_stripped) > available_width:
                # Truncate with ellipsis
                truncated = line_stripped[:available_width - 3] + "..."
                content.append(truncated + "\n", style="brand")
            else:
                content.append(line + "\n", style="brand")
    else:
        # Narrow terminal - use compact text version
        content.append("STRUCTURED\n", style="brand")
        content.append("  ────────\n", style="brand")
    
    content.append(brand.subtitle + "\n", style="muted")
    
    # Wrap tagline if needed
    tagline_text = TAGLINE
    if len(tagline_text) > available_width:
        # Simple word wrap for tagline
        words = tagline_text.split()
        wrapped_lines = []
        current_line = ""
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if len(test_line) <= available_width:
                current_line = test_line
            else:
                if current_line:
                    wrapped_lines.append(current_line)
                current_line = word
        if current_line:
            wrapped_lines.append(current_line)
        tagline_text = "\n".join(wrapped_lines)
    
    content.append(tagline_text, style="muted")

    # Panel automatically fits to terminal width
    # Adjust padding based on terminal size
    padding_h = 2 if terminal_width >= 100 else 1
    padding_v = 1 if terminal_height >= 25 else 0
    
    return Panel(
        content,
        box=box.SQUARE,
        border_style="frame",
        padding=(padding_v, padding_h),
        title=f"[muted]{brand.version}[/muted]",
        title_align="right",
    )


def print_banner(console: Console, brand: BrandInfo = BrandInfo()) -> None:
    if _no_color_enabled():
        console.print("Welcome to")
        # Adjust for plain output too
        width = _get_terminal_width(console)
        max_wordmark_width = max(len(line.rstrip()) for line in WORDMARK)
        
        if width >= max_wordmark_width:
            for line in WORDMARK:
                console.print(line)
        elif width >= 50:
            for line in WORDMARK:
                line_stripped = line.rstrip()
                if len(line_stripped) > width:
                    console.print(line_stripped[:width - 3] + "...")
                else:
                    console.print(line)
        else:
            console.print("STRUCTURED")
        console.print(TAGLINE)
        return

    console.push_theme(THEME)
    console.print(build_banner(console, brand))
    console.pop_theme()
