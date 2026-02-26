"""
Document loading and transformation.

Load from paths or connectors → Documents; optionally transform to Nodes
via chunking for indexing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.indexing.documents import Document, Node
from structure_d.ingestion.manager import IngestionManager
from structure_d.preprocessing.chunker import Chunker
from structure_d.preprocessing.normalizer import normalize_text
from structure_d.schemas.base import DocumentFormat, ParsedDocument, TextChunk

logger = structlog.get_logger(__name__)


class DocumentReader:
    """
    Load documents from paths and optionally chunk into nodes.

    Usage::

        reader = DocumentReader()
        docs = await reader.load(path)           # List[Document]
        nodes = await reader.load_and_chunk(path)  # List[Node], ready for index
    """

    def __init__(
        self,
        ingestion_manager: IngestionManager | None = None,
        chunker: Chunker | None = None,
    ) -> None:
        settings = get_settings()
        self.ingestion = ingestion_manager or IngestionManager()
        self.chunker = chunker or Chunker(
            strategy=settings.preprocessing.chunking.strategy,
            max_tokens=settings.preprocessing.chunking.max_tokens,
            overlap_tokens=settings.preprocessing.chunking.overlap_tokens,
            heading_level=settings.preprocessing.chunking.heading_level,
        )

    async def load(self, path: Path | str, parser_name: str | None = None) -> list[Document]:
        """
        Load a single file into one or more Documents (one Document per parsed doc).
        """
        fp = Path(path)
        if not fp.exists():
            raise FileNotFoundError(f"Path not found: {fp}")
        parsed: ParsedDocument = await self.ingestion.ingest(fp, parser_name=parser_name)
        text = normalize_text(
            parsed.text,
            normalize_unicode=get_settings().preprocessing.normalize_unicode,
            strip_boilerplate=get_settings().preprocessing.strip_boilerplate,
        )
        doc = Document.from_parsed(parsed)
        doc.text = text
        return [doc]

    async def load_and_chunk(
        self,
        path: Path | str,
        parser_name: str | None = None,
    ) -> list[Node]:
        """
        Load file, normalize, chunk, and return Nodes ready for indexing.
        """
        docs = await self.load(path, parser_name=parser_name)
        if not docs:
            return []
        doc = docs[0]
        chunks: list[TextChunk] = self.chunker.chunk(
            doc.text,
            document_id=doc.id,
        )
        try:
            fmt = DocumentFormat(doc.metadata.get("format", "unknown"))
        except ValueError:
            fmt = DocumentFormat.UNKNOWN
        for c in chunks:
            c.metadata.source_format = fmt
        nodes = [Node.from_text_chunk(c) for c in chunks]
        logger.info("load_and_chunk", path=str(path), nodes=len(nodes))
        return nodes

    async def load_directory(
        self,
        directory: Path | str,
        glob: str = "**/*",
        parser_name: str | None = None,
    ) -> list[Document]:
        """Load all supported files in a directory into Documents."""
        base = Path(directory)
        if not base.is_dir():
            raise NotADirectoryError(f"Not a directory: {base}")
        exts = get_settings().ingestion.supported_extensions
        docs: list[Document] = []
        for fp in base.glob(glob):
            if fp.is_file() and any(fp.suffix.lower() == e.lower() for e in exts):
                try:
                    docs.extend(await self.load(fp, parser_name=parser_name))
                except Exception as e:
                    logger.warning("load_skipped", path=str(fp), error=str(e))
        return docs

    async def load_directory_and_chunk(
        self,
        directory: Path | str,
        glob: str = "**/*",
        parser_name: str | None = None,
    ) -> list[Node]:
        """Load all supported files in a directory and return Nodes."""
        docs = await self.load_directory(directory, glob=glob, parser_name=parser_name)
        nodes: list[Node] = []
        for doc in docs:
            chunks = self.chunker.chunk(doc.text, document_id=doc.id)
            try:
                fmt = DocumentFormat(doc.metadata.get("format", "unknown"))
            except ValueError:
                fmt = DocumentFormat.UNKNOWN
            for c in chunks:
                c.metadata.source_format = fmt
            nodes.extend(Node.from_text_chunk(c) for c in chunks)
        logger.info("load_directory_and_chunk", directory=str(directory), nodes=len(nodes))
        return nodes
