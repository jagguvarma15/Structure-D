"""
Main interactive terminal application.

Provides a logo, animated initialization, and an interactive REPL
with autocompletion.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from structure_d import __version__
from structure_d.terminal.banner import HELP_TEXT, LOGO, TAGLINE, WELCOME
from structure_d.terminal.completer import StructureDCompleter

console = Console()

# Prompt style
_PROMPT_STYLE = Style.from_dict({
    "prompt": "bold ansicyan",
    "arrow": "bold ansigreen",
})


def _prompt_message() -> HTML:
    return HTML("<prompt>structure-d</prompt> <arrow>❯</arrow> ")


class TerminalApp:
    """
    Interactive terminal for Structure-D.

    Displays a logo, runs initialization checks, and drops into
    a command loop with autocompletion.
    """

    def __init__(self) -> None:
        self.session = PromptSession(
            history=InMemoryHistory(),
            completer=StructureDCompleter(),
            style=_PROMPT_STYLE,
            complete_while_typing=True,
        )

    def run(self) -> None:
        """Entry point: show banner, init, then REPL."""
        self._show_banner()
        self._initialize()
        console.print(WELCOME)
        asyncio.run(self._repl())

    # ── Banner ────────────────────────────────────────────────────────────────

    def _show_banner(self) -> None:
        console.print(LOGO)
        console.print(f"  [bold white]v{__version__}[/bold white]   {TAGLINE}")
        console.print()

    # ── Initialization ────────────────────────────────────────────────────────

    def _initialize(self) -> None:
        """Show animated init steps."""
        from rich.progress import Progress, SpinnerColumn, TextColumn

        steps = [
            ("Loading configuration", self._init_config),
            ("Loading model registry", self._init_models),
            ("Discovering parsers", self._init_parsers),
            ("Checking vLLM server", self._init_vllm),
            ("Ready", lambda: None),
        ]

        console.print("[bold]Initializing...[/bold]\n")

        with Progress(
            SpinnerColumn("dots"),
            TextColumn("[bold]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            for desc, fn in steps:
                task = progress.add_task(desc, total=1)
                fn()
                time.sleep(0.15)  # brief pause for visual effect
                progress.update(task, completed=1)

        # Print summary
        from structure_d.config import get_settings
        from structure_d.models.registry import ModelRegistry
        from structure_d.schemas.base import _EXT_TO_FORMAT
        from structure_d.schemas.generic import BUILTIN_SCHEMAS

        settings = get_settings()
        registry = ModelRegistry.from_yaml(settings.models.registry_path)
        n_models = len(registry.list_models())
        n_schemas = len(BUILTIN_SCHEMAS)
        n_formats = len(set(_EXT_TO_FORMAT.values()))

        summary = (
            f"  [green]✓[/green] Config loaded        [dim]({settings.project_name})[/dim]\n"
            f"  [green]✓[/green] Models registered    [dim]({n_models} models)[/dim]\n"
            f"  [green]✓[/green] Schemas available    [dim]({n_schemas} built-in)[/dim]\n"
            f"  [green]✓[/green] Formats supported    [dim]({n_formats} types)[/dim]\n"
            f"  [green]✓[/green] vLLM endpoint        [dim]({settings.inference.vllm.api_base})[/dim]"
        )
        console.print(Panel(summary, title="[bold green]System Ready[/bold green]", border_style="green", padding=(0, 1)))
        console.print()

    @staticmethod
    def _init_config() -> None:
        from structure_d.config import get_settings
        get_settings()

    @staticmethod
    def _init_models() -> None:
        from structure_d.config import get_settings
        from structure_d.models.registry import ModelRegistry
        settings = get_settings()
        ModelRegistry.from_yaml(settings.models.registry_path)

    @staticmethod
    def _init_parsers() -> None:
        from structure_d.ingestion.manager import build_default_registry
        build_default_registry()

    @staticmethod
    def _init_vllm() -> None:
        # Non-blocking check; we just validate the URL is configured
        from structure_d.config import get_settings
        get_settings().inference.vllm.api_base

    # ── REPL ──────────────────────────────────────────────────────────────────

    async def _repl(self) -> None:
        """Interactive command loop."""
        from structure_d.terminal.commands import (
            cmd_batch,
            cmd_config,
            cmd_extract,
            cmd_formats,
            cmd_models,
            cmd_schemas,
            cmd_status,
        )

        while True:
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.session.prompt(_prompt_message()),
                )
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                break

            raw = raw.strip()
            if not raw:
                continue

            try:
                parts = shlex.split(raw)
            except ValueError:
                parts = raw.split()

            cmd = parts[0].lower()
            args = parts[1:]

            try:
                if cmd in ("exit", "quit"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                elif cmd == "help":
                    console.print(HELP_TEXT)
                elif cmd == "clear":
                    console.clear()
                    self._show_banner()
                elif cmd == "version":
                    console.print(f"[bold]Structure-D[/bold] v{__version__}")
                elif cmd == "extract":
                    await cmd_extract(args)
                elif cmd == "batch":
                    await cmd_batch(args)
                elif cmd == "models":
                    cmd_models()
                elif cmd == "schemas":
                    cmd_schemas()
                elif cmd == "formats":
                    cmd_formats()
                elif cmd == "config":
                    cmd_config()
                elif cmd == "status":
                    await cmd_status()
                else:
                    console.print(
                        f"[red]Unknown command:[/red] {cmd}\n"
                        f"[dim]Type [bold]help[/bold] to see available commands.[/dim]"
                    )
            except Exception as exc:
                console.print(f"[bold red]Error:[/bold red] {exc}")
