"""ASCII banner and branding for the terminal UI."""

from __future__ import annotations

LOGO = r"""
[bold cyan]
  ╔═╗╔╦╗╦═╗╦ ╦╔═╗╔╦╗╦ ╦╦═╗╔═╗  ╔═╗
  ╚═╗ ║ ╠╦╝║ ║║   ║ ║ ║╠╦╝║╣   ║ ║
  ╚═╝ ╩ ╩╚═╚═╝╚═╝ ╩ ╚═╝╩╚═╚═╝  ╚═╝
[/bold cyan]"""

TAGLINE = "[dim]Unstructured → Structured  ·  Any format, any schema, high-throughput vLLM inference[/dim]"

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
