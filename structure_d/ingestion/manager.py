"""High-level ingestion manager that orchestrates connectors and parsers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog

from structure_d.config import get_settings
from structure_d.ingestion.audio import TranscriptParser
from structure_d.ingestion.base import BaseParser, ParserRegistry
from structure_d.ingestion.connectors import BaseConnector, LocalConnector
from structure_d.ingestion.email_parser import EmailParser
from structure_d.ingestion.html_parser import HTMLParser
from structure_d.ingestion.image import TesseractImageParser
from structure_d.ingestion.office import DocxParser, PptxParser, XlsxParser
from structure_d.ingestion.pdf import OCRPDFParser, PDFPlumberParser, PyMuPDFParser
from structure_d.ingestion.text import PlainTextParser
from structure_d.schemas.base import ParsedDocument, detect_format

logger = structlog.get_logger(__name__)


def build_default_registry() -> ParserRegistry:
    """Create a registry pre-populated with all built-in parsers."""
    settings = get_settings()
    registry = ParserRegistry()

    # PDF parsers – preference order
    registry.register("pymupdf", PyMuPDFParser())
    registry.register("pdfplumber", PDFPlumberParser())
    registry.register(
        "ocr_pdf",
        OCRPDFParser(languages=settings.ingestion.ocr_languages),
    )

    # Images
    registry.register(
        "tesseract_image",
        TesseractImageParser(languages=settings.ingestion.ocr_languages),
    )

    # HTML
    registry.register("html", HTMLParser())

    # Office
    registry.register("docx", DocxParser())
    registry.register("xlsx", XlsxParser())
    registry.register("pptx", PptxParser())

    # Email
    registry.register("email", EmailParser())

    # Transcripts
    registry.register("transcript", TranscriptParser())

    # Plain text / Markdown / CSV
    registry.register("plaintext", PlainTextParser())

    return registry


class IngestionManager:
    """
    Orchestrates file discovery, download and parsing.

    Usage::

        manager = IngestionManager()
        doc = await manager.ingest(Path("invoice.pdf"))
    """

    def __init__(
        self,
        registry: ParserRegistry | None = None,
        connector: BaseConnector | None = None,
    ) -> None:
        self.registry = registry or build_default_registry()
        self.connector = connector or LocalConnector()

    async def ingest(self, file_path: Path, parser_name: str | None = None) -> ParsedDocument:
        """Parse a single local file."""
        settings = get_settings()
        ext = file_path.suffix.lower()

        if ext not in settings.ingestion.supported_extensions:
            raise ParserError(
                f"Unsupported file extension {ext!r}",
                file_path=str(file_path),
                format=ext,
                context={
                    "supported": ", ".join(settings.ingestion.supported_extensions),
                },
            )

        parser = self._resolve_parser(file_path, parser_name)
        fmt = detect_format(ext)
        logger.info(
            "ingesting_file",
            path=str(file_path),
            format=fmt.value,
            parser=type(parser).__name__,
        )
        doc = await parser.parse(file_path)
        doc.metadata.format = fmt
        return doc

    async def ingest_many(
        self,
        file_paths: list[Path],
        parser_name: str | None = None,
    ) -> list[ParsedDocument]:
        """Parse multiple files sequentially (async per-file)."""
        results: list[ParsedDocument] = []
        for fp in file_paths:
            doc = await self.ingest(fp, parser_name=parser_name)
            results.append(doc)
        return results

    async def ingest_from_connector(
        self,
        prefix: str = "",
        parser_name: str | None = None,
    ) -> list[ParsedDocument]:
        """
        Discover files via the connector, download to a temp dir, parse.
        """
        keys = await self.connector.list_files(prefix)
        results: list[ParsedDocument] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for key in keys:
                local_path = await self.connector.download(key, tmp)
                doc = await self.ingest(local_path, parser_name=parser_name)
                results.append(doc)

        return results

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_parser(self, file_path: Path, parser_name: str | None) -> BaseParser:
        if parser_name:
            parser = self.registry.get(parser_name)
            if parser is None:
                raise ParserError(
                    f"Parser {parser_name!r} not found",
                    parser_name=parser_name,
                    file_path=str(file_path),
                    context={
                        "available": ", ".join(self.registry.list_parsers()),
                    },
                )
            return parser

        # Auto-select
        parser = self.registry.get_for_file(file_path)
        if parser is None:
            raise ParserError(
                f"No parser registered for {file_path.suffix!r}",
                file_path=str(file_path),
                format=file_path.suffix,
                context={
                    "available": ", ".join(self.registry.list_parsers()),
                },
            )
        return parser
