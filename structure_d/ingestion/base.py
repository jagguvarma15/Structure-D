"""Base parser interface and parser registry."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from structure_d.schemas.base import ParsedDocument


class BaseParser(abc.ABC):
    """Abstract interface every document parser must implement."""

    #: File extensions this parser can handle (e.g. [".pdf", ".PDF"]).
    supported_extensions: list[str] = []

    @abc.abstractmethod
    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        """Parse *file_path* and return a :class:`ParsedDocument`."""

    def can_handle(self, file_path: Path) -> bool:
        """Return ``True`` if this parser supports the file's extension."""
        return file_path.suffix.lower() in [e.lower() for e in self.supported_extensions]


class ParserRegistry:
    """Registry of available parsers, keyed by name."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}

    def register(self, name: str, parser: BaseParser) -> None:
        self._parsers[name] = parser

    def get(self, name: str) -> BaseParser | None:
        return self._parsers.get(name)

    def get_for_file(self, file_path: Path) -> BaseParser | None:
        """Return the first registered parser that can handle *file_path*."""
        for parser in self._parsers.values():
            if parser.can_handle(file_path):
                return parser
        return None

    def list_parsers(self) -> list[str]:
        return list(self._parsers.keys())

    # Convenience: iterate
    def __iter__(self):  # noqa: ANN204
        return iter(self._parsers.items())
