"""HTML / web page parsing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from structure_d.ingestion.base import BaseParser
from structure_d.schemas.base import DocumentFormat, DocumentMetadata, ParsedDocument

logger = structlog.get_logger(__name__)

# Tags whose entire subtree we throw away.
_SKIP_TAGS = frozenset(
    ["script", "style", "noscript", "svg", "canvas", "nav", "footer", "aside", "head"]
)

# Block-level leaf tags — we pull `.get_text()` and stop recursing.
_LEAF_BLOCKS = frozenset(
    ["p", "pre", "blockquote", "figcaption", "caption", "dt", "dd"]
)

_HEADING_LEVEL: dict[str, int] = {f"h{n}": n for n in range(1, 7)}
_HEADING_MARKER: dict[int, str] = {n: "#" * n for n in range(1, 7)}


class HTMLParser(BaseParser):
    """Parse HTML files using BeautifulSoup.

    Extracts:
    - Paragraph and heading text with Markdown-style heading markers
    - Tables as structured ``{"index": n, "headers": [...], "data": [[...]]}`` records
    - All ``<meta>`` tags (description, keywords, author, Open Graph) into ``extra``
    - Hyperlinks as ``extra["links"]``
    - Section-based pages split at every H1 / H2 boundary
    """

    supported_extensions = [".html", ".htm"]

    def __init__(self, parser_lib: str = "lxml") -> None:
        self.parser_lib = parser_lib

    async def parse(self, file_path: Path, **kwargs: object) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise ImportError(
                "beautifulsoup4 is required for HTML parsing. "
                "Install with: pip install 'structure-d[ingestion]'"
            ) from exc

        raw = file_path.read_text(encoding="utf-8", errors="replace")

        try:
            soup = BeautifulSoup(raw, self.parser_lib)
        except Exception:
            soup = BeautifulSoup(raw, "html.parser")

        extra = self._extract_meta(soup)
        links = self._extract_links(soup)
        if links:
            extra["links"] = links

        tables = self._extract_tables(soup)

        # Remove tables from the tree so they don't bleed into body text.
        for tbl in soup.find_all("table"):
            tbl.decompose()

        full_text, sections = self._build_text(soup)

        logger.debug(
            "html.parsed",
            filename=file_path.name,
            sections=len(sections),
            tables=len(tables),
            chars=len(full_text),
        )

        metadata = DocumentMetadata(
            filename=file_path.name,
            source=str(file_path),
            file_extension=file_path.suffix.lower(),
            format=DocumentFormat.HTML,
            file_size_bytes=file_path.stat().st_size,
            extra=extra,
        )

        return ParsedDocument(
            metadata=metadata,
            text=full_text,
            pages=sections if sections else [full_text],
            tables=tables,
        )

    # ── Structured text ───────────────────────────────────────────────────────

    @staticmethod
    def _build_text(soup: object) -> tuple[str, list[str]]:
        """Walk the body in DOM order and return ``(full_text, sections)``.

        Sections are split at every H1 / H2 boundary so that
        ``ParsedDocument.pages`` maps to meaningful content chunks.
        """
        from bs4 import NavigableString, Tag

        parts: list[str] = []
        section_buf: list[str] = []
        sections: list[str] = []

        def flush() -> None:
            if section_buf:
                sections.append("\n\n".join(section_buf))
                section_buf.clear()

        def walk(node: object) -> None:
            if isinstance(node, NavigableString):
                return
            if not isinstance(node, Tag):
                return

            tag = (node.name or "").lower()

            if tag in _SKIP_TAGS:
                return

            if tag in _HEADING_LEVEL:
                text = node.get_text(strip=True)
                if text:
                    level = _HEADING_LEVEL[tag]
                    if level <= 2:
                        flush()
                    line = f"{_HEADING_MARKER[level]} {text}"
                    parts.append(line)
                    section_buf.append(line)
                return  # do not recurse into heading children

            if tag == "table":
                return  # already extracted separately

            if tag in ("ul", "ol"):
                items = [
                    f"- {li.get_text(separator=' ', strip=True)}"
                    for li in node.find_all("li", recursive=False)
                    if li.get_text(strip=True)
                ]
                if items:
                    block = "\n".join(items)
                    parts.append(block)
                    section_buf.append(block)
                return

            if tag in _LEAF_BLOCKS:
                text = node.get_text(separator=" ", strip=True)
                if text:
                    parts.append(text)
                    section_buf.append(text)
                return

            # Generic container — recurse into children.
            for child in node.children:
                walk(child)

        body = soup.find("body") or soup
        for child in body.children:
            walk(child)

        flush()
        return "\n\n".join(parts), sections

    # ── Tables ────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_tables(soup: object) -> list[dict[str, Any]]:
        """Return every ``<table>`` as ``{"index": n, "headers": [...], "data": [[...]]}"``."""
        tables: list[dict[str, Any]] = []

        for idx, table in enumerate(soup.find_all("table")):
            headers: list[str] = []
            thead = table.find("thead")
            if thead:
                headers = [th.get_text(strip=True) for th in thead.find_all("th")]

            rows: list[list[str]] = []
            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                cells = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
                if any(cells):
                    rows.append(cells)

            if headers or rows:
                tables.append({"index": idx, "headers": headers, "data": rows})

        return tables

    # ── Metadata ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_meta(soup: object) -> dict[str, Any]:
        """Collect ``<title>`` and all ``<meta>`` content into a flat dict."""
        extra: dict[str, Any] = {}

        if soup.title and soup.title.string:
            extra["title"] = soup.title.string.strip()

        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower().strip()
            prop = (meta.get("property") or "").lower().strip()
            content = (meta.get("content") or "").strip()
            if not content:
                continue
            if name in ("description", "keywords", "author", "robots", "viewport"):
                extra[name] = content
            elif prop.startswith("og:"):
                extra[f"og_{prop[3:]}"] = content

        return extra

    # ── Links ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_links(soup: object) -> list[dict[str, str]]:
        """Return all non-anchor, non-javascript ``<a href>`` links."""
        links: list[dict[str, str]] = []
        for a in soup.find_all("a", href=True):
            href: str = a["href"].strip()
            if not href or href.startswith(("#", "javascript:")):
                continue
            links.append({"text": a.get_text(strip=True), "href": href})
        return links
