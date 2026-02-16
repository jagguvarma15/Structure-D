"""Prompt-toolkit completer for the interactive terminal."""

from __future__ import annotations

import os
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# Top-level commands
_COMMANDS = [
    "extract",
    "batch",
    "models",
    "schemas",
    "formats",
    "config",
    "status",
    "clear",
    "version",
    "help",
    "exit",
    "quit",
]

_SCHEMA_NAMES = [
    "generic",
    "key_value",
    "table",
    "entity",
    "classification",
    "summary",
    "form",
    "document_structure",
]

_TASK_NAMES = [
    "extraction",
    "classification",
    "summarisation",
    "sentiment",
]

_FLAGS = {
    "extract": ["--schema", "--task", "--model", "--format", "--output"],
    "batch": ["--schema", "--format"],
}


class StructureDCompleter(Completer):
    """Context-aware autocomplete for the Structure-D REPL."""

    def get_completions(self, document: Document, complete_event: object) -> ...:
        text = document.text_before_cursor
        words = text.split()
        word_before = document.get_word_before_cursor()

        # Empty or first word → complete command
        if not words or (len(words) == 1 and not text.endswith(" ")):
            for cmd in _COMMANDS:
                if cmd.startswith(word_before):
                    yield Completion(cmd, start_position=-len(word_before))
            return

        cmd = words[0]

        # If the previous word is a flag that expects a value
        if len(words) >= 2:
            prev = words[-1] if text.endswith(" ") else (words[-2] if len(words) >= 2 else "")
            if not text.endswith(" "):
                prev = words[-2] if len(words) >= 3 else words[-1]

            completing_value = text.endswith(" ") and len(words) >= 2

            # Decide what the previous token is
            prev_token = words[-1] if text.endswith(" ") else (words[-2] if len(words) >= 2 else "")

            if prev_token == "--schema":
                for s in _SCHEMA_NAMES:
                    if s.startswith(word_before):
                        yield Completion(s, start_position=-len(word_before))
                return

            if prev_token == "--task":
                for t in _TASK_NAMES:
                    if t.startswith(word_before):
                        yield Completion(t, start_position=-len(word_before))
                return

            if prev_token == "--format":
                for f in ["jsonl", "csv"]:
                    if f.startswith(word_before):
                        yield Completion(f, start_position=-len(word_before))
                return

        # Flags for commands
        if cmd in _FLAGS and word_before.startswith("-"):
            for flag in _FLAGS[cmd]:
                if flag.startswith(word_before) and flag not in words:
                    yield Completion(flag, start_position=-len(word_before))
            return

        # File/directory completion for extract and batch
        if cmd in ("extract", "batch"):
            # Only complete if we're not completing a flag
            if not word_before.startswith("-"):
                yield from self._complete_path(word_before)
                return

        # Flag completion
        if cmd in _FLAGS and (text.endswith(" ") or word_before.startswith("-")):
            prefix = word_before if word_before.startswith("-") else ""
            for flag in _FLAGS.get(cmd, []):
                if flag.startswith(prefix) and flag not in words:
                    yield Completion(flag, start_position=-len(prefix))

    @staticmethod
    def _complete_path(prefix: str) -> list[Completion]:
        """Complete file/directory paths."""
        completions: list[Completion] = []
        p = Path(prefix) if prefix else Path(".")

        try:
            if prefix and not prefix.endswith("/"):
                parent = p.parent
                partial = p.name
            else:
                parent = p if p.is_dir() else p.parent
                partial = ""

            if parent.exists():
                for entry in sorted(parent.iterdir()):
                    name = entry.name
                    if name.startswith("."):
                        continue
                    if partial and not name.lower().startswith(partial.lower()):
                        continue
                    display = f"{name}/" if entry.is_dir() else name
                    full = str(parent / name) if str(parent) != "." else name
                    if entry.is_dir():
                        full += "/"
                    completions.append(
                        Completion(full, start_position=-len(prefix), display=display)
                    )
        except PermissionError:
            pass

        return completions
