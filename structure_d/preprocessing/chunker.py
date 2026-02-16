"""Text chunking strategies."""

from __future__ import annotations

import re
from typing import Literal

import structlog

from structure_d.schemas.base import ChunkMetadata, TextChunk

logger = structlog.get_logger(__name__)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


class Chunker:
    """
    Split text into chunks with configurable strategy.

    Strategies
    ----------
    fixed   – split every *max_tokens* tokens with overlap.
    sentence – split on sentence boundaries.
    heading – split on Markdown / document headings.
    semantic – sentence-based with heading-awareness (default).
    """

    def __init__(
        self,
        strategy: Literal["fixed", "sentence", "heading", "semantic"] = "semantic",
        max_tokens: int = 1024,
        overlap_tokens: int = 128,
        heading_level: int = 2,
    ) -> None:
        self.strategy = strategy
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.heading_level = heading_level

    def chunk(self, text: str, document_id: str = "") -> list[TextChunk]:
        """Split *text* into :class:`TextChunk` objects."""
        if self.strategy == "fixed":
            return self._chunk_fixed(text, document_id)
        elif self.strategy == "sentence":
            return self._chunk_sentence(text, document_id)
        elif self.strategy == "heading":
            return self._chunk_heading(text, document_id)
        elif self.strategy == "semantic":
            return self._chunk_semantic(text, document_id)
        else:
            raise ValueError(f"Unknown chunking strategy: {self.strategy!r}")

    # ── Fixed-size chunking ───────────────────────────────────────────────────

    def _chunk_fixed(self, text: str, document_id: str) -> list[TextChunk]:
        max_chars = self.max_tokens * 4
        overlap_chars = self.overlap_tokens * 4
        chunks: list[TextChunk] = []
        start = 0

        while start < len(text):
            end = min(start + max_chars, len(text))
            segment = text[start:end]

            chunks.append(
                TextChunk(
                    text=segment,
                    metadata=ChunkMetadata(
                        document_id=document_id,
                        start_char=start,
                        end_char=end,
                        token_count=_estimate_tokens(segment),
                    ),
                )
            )

            if end >= len(text):
                break
            start = end - overlap_chars

        return chunks

    # ── Sentence-based chunking ───────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences using a simple regex heuristic."""
        # Split on sentence-ending punctuation followed by whitespace
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in parts if s.strip()]

    def _chunk_sentence(self, text: str, document_id: str) -> list[TextChunk]:
        sentences = self._split_sentences(text)
        return self._group_segments(sentences, text, document_id)

    # ── Heading-based chunking ────────────────────────────────────────────────

    def _chunk_heading(self, text: str, document_id: str) -> list[TextChunk]:
        # Split on Markdown headings up to the configured level
        pattern = r"(?m)^(#{1," + str(self.heading_level) + r"})\s+"
        parts = re.split(pattern, text)

        sections: list[tuple[str | None, str]] = []
        i = 0
        while i < len(parts):
            if re.match(r"^#{1,6}$", parts[i].strip()) and i + 1 < len(parts):
                heading = parts[i].strip()
                body = parts[i + 1]
                sections.append((heading, body))
                i += 2
            else:
                sections.append((None, parts[i]))
                i += 1

        chunks: list[TextChunk] = []
        for heading, body in sections:
            body = body.strip()
            if not body:
                continue
            tokens = _estimate_tokens(body)
            if tokens <= self.max_tokens:
                chunks.append(
                    TextChunk(
                        text=body,
                        metadata=ChunkMetadata(
                            document_id=document_id,
                            heading=heading,
                            token_count=tokens,
                        ),
                    )
                )
            else:
                # Sub-chunk large sections by sentence
                sub = self._chunk_sentence(body, document_id)
                for c in sub:
                    c.metadata.heading = heading
                chunks.extend(sub)
        return chunks

    # ── Semantic (sentence + heading-aware) ───────────────────────────────────

    def _chunk_semantic(self, text: str, document_id: str) -> list[TextChunk]:
        """Combine heading and sentence strategies: split on headings first, then sentences."""
        heading_pattern = re.compile(
            r"(?m)^(#{1," + str(self.heading_level) + r"})\s+(.+)$"
        )
        sections: list[tuple[str | None, str]] = []
        last_end = 0
        current_heading: str | None = None

        for m in heading_pattern.finditer(text):
            if m.start() > last_end:
                sections.append((current_heading, text[last_end : m.start()]))
            current_heading = m.group(2).strip()
            last_end = m.end()

        if last_end < len(text):
            sections.append((current_heading, text[last_end:]))

        # If no headings found, fall back to sentence chunking
        if len(sections) <= 1 and sections and sections[0][0] is None:
            return self._chunk_sentence(text, document_id)

        chunks: list[TextChunk] = []
        for heading, body in sections:
            body = body.strip()
            if not body:
                continue
            sentences = self._split_sentences(body)
            sub_chunks = self._group_segments(sentences, body, document_id)
            for c in sub_chunks:
                c.metadata.heading = heading
            chunks.extend(sub_chunks)

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _group_segments(
        self, segments: list[str], full_text: str, document_id: str
    ) -> list[TextChunk]:
        """Group sentences/segments into chunks that fit within max_tokens."""
        chunks: list[TextChunk] = []
        current_parts: list[str] = []
        current_tokens = 0

        for seg in segments:
            seg_tokens = _estimate_tokens(seg)
            if current_tokens + seg_tokens > self.max_tokens and current_parts:
                chunk_text = " ".join(current_parts)
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        metadata=ChunkMetadata(
                            document_id=document_id,
                            token_count=_estimate_tokens(chunk_text),
                        ),
                    )
                )
                # Overlap: keep last few parts
                overlap_parts: list[str] = []
                overlap_tok = 0
                for part in reversed(current_parts):
                    pt = _estimate_tokens(part)
                    if overlap_tok + pt > self.overlap_tokens:
                        break
                    overlap_parts.insert(0, part)
                    overlap_tok += pt
                current_parts = overlap_parts
                current_tokens = overlap_tok

            current_parts.append(seg)
            current_tokens += seg_tokens

        if current_parts:
            chunk_text = " ".join(current_parts)
            chunks.append(
                TextChunk(
                    text=chunk_text,
                    metadata=ChunkMetadata(
                        document_id=document_id,
                        token_count=_estimate_tokens(chunk_text),
                    ),
                )
            )

        return chunks
