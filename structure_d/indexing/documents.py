"""
Document and Node abstractions.

Documents are generic containers for any data source; Nodes represent chunks
of source Documents with inherited and chunk-level metadata.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from structure_d.schemas.base import ParsedDocument, TextChunk


class Document(BaseModel):
    """
    Generic document container for any data source.

    Raw content + metadata. Can be built from
    :class:`ParsedDocument` or from raw text + metadata.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="Unique document ID")
    text: str = Field(default="", description="Raw document content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Source metadata")
    extra: dict[str, Any] = Field(default_factory=dict, description="Custom attributes")

    @classmethod
    def from_parsed(cls, doc: ParsedDocument) -> Document:
        """Build a Document from a pipeline ParsedDocument."""
        meta = doc.metadata.model_dump() if hasattr(doc.metadata, "model_dump") else {}
        return cls(
            id=doc.metadata.document_id,
            text=doc.text,
            metadata=meta,
            extra={"pages": getattr(doc, "pages", []), "format": str(doc.metadata.format)},
        )


class Node(BaseModel):
    """
    A chunk of a source Document with metadata.

    Used by indexes for retrieval and by query engines for context.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="Unique node ID")
    text: str = Field(default="", description="Chunk text")
    document_id: str = Field(default="", description="Parent document ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Chunk-level metadata")
    extra: dict[str, Any] = Field(default_factory=dict, description="Custom attributes")

    @classmethod
    def from_text_chunk(cls, chunk: TextChunk) -> Node:
        """Build a Node from a pipeline TextChunk."""
        meta = chunk.metadata.model_dump() if hasattr(chunk.metadata, "model_dump") else {}
        return cls(
            id=chunk.metadata.chunk_id,
            text=chunk.text,
            document_id=chunk.metadata.document_id,
            metadata=meta,
        )

    def to_retrieval_result(self, score: float | None = None) -> dict[str, Any]:
        """Convert to retrieval result dict (document, metadata, distance)."""
        out: dict[str, Any] = {
            "id": self.id,
            "document": self.text,
            "metadata": self.metadata,
        }
        if score is not None:
            out["distance"] = 1.0 - score if score <= 1.0 else score
        elif self.extra.get("distance") is not None:
            out["distance"] = self.extra["distance"]
        return out
