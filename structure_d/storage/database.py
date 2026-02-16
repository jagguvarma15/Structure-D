"""Database storage (PostgreSQL + optional PGVector)."""

from __future__ import annotations

import json
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.schemas.base import ExtractionResult

logger = structlog.get_logger(__name__)


class DatabaseWriter:
    """
    Persist extraction results to a relational database via SQLAlchemy.

    Requires the ``storage`` extra: ``pip install structure-d[storage]``.

    The writer creates tables on first use and appends rows.
    """

    def __init__(self, connection_string: str | None = None, table_prefix: str | None = None) -> None:
        settings = get_settings()
        self.connection_string = connection_string or settings.storage.database.connection_string
        self.table_prefix = table_prefix or settings.storage.database.table_prefix
        self._engine = None
        self._session_factory = None

    def _ensure_engine(self) -> None:
        if self._engine is not None:
            return
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            # Use sync engine for simplicity; async variant available via asyncpg
            sync_url = self.connection_string.replace("+asyncpg", "")
            self._engine = create_engine(sync_url, echo=False)
            self._session_factory = sessionmaker(bind=self._engine)
        except ImportError as e:
            raise ImportError(
                "Database storage requires sqlalchemy. "
                "Install with: pip install structure-d[storage]"
            ) from e

    def _ensure_table(self) -> None:
        self._ensure_engine()
        from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, Text, Boolean

        metadata = MetaData()
        self._table = Table(
            f"{self.table_prefix}results",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("result_id", String(64), unique=True, index=True),
            Column("document_id", String(64), index=True),
            Column("chunk_id", String(64), nullable=True),
            Column("task", String(32)),
            Column("model_used", String(256)),
            Column("is_valid", Boolean, default=False),
            Column("structured_output", Text),  # JSON string
            Column("raw_output", Text),
            Column("validation_errors", Text),
            Column("latency_ms", Float),
            Column("token_usage", Text),
            Column("created_at", DateTime),
        )
        metadata.create_all(self._engine)

    def write(self, results: list[ExtractionResult]) -> int:
        """Insert *results* into the database.  Returns count of rows inserted."""
        self._ensure_table()

        rows = []
        for r in results:
            rows.append({
                "result_id": r.result_id,
                "document_id": r.document_id,
                "chunk_id": r.chunk_id,
                "task": r.task.value,
                "model_used": r.model_used,
                "is_valid": r.is_valid,
                "structured_output": json.dumps(r.structured_output, default=str),
                "raw_output": r.raw_output,
                "validation_errors": json.dumps(r.validation_errors),
                "latency_ms": r.latency_ms,
                "token_usage": json.dumps(r.token_usage),
                "created_at": r.created_at,
            })

        with self._session_factory() as session:
            session.execute(self._table.insert(), rows)
            session.commit()

        logger.info("database_written", count=len(rows))
        return len(rows)
