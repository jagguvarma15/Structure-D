"""Database storage (PostgreSQL + optional PGVector)."""

from __future__ import annotations

import json
from typing import Any

import structlog

from structure_d.config import get_settings
from structure_d.exceptions import StorageError
from structure_d.schemas.base import ExtractionResult

logger = structlog.get_logger(__name__)


class DatabaseWriter:
    """
    Persist extraction results to a relational database via async SQLAlchemy.

    Requires the ``storage`` extra: ``pip install structure-d[storage]``.

    The writer creates tables on first use and appends rows.
    """

    def __init__(self, connection_string: str | None = None, table_prefix: str | None = None) -> None:
        settings = get_settings()
        self.connection_string = connection_string or settings.storage.database.connection_string
        self.table_prefix = table_prefix or settings.storage.database.table_prefix
        self._engine = None
        self._table = None
        self._initialized = False

    async def _ensure_engine(self) -> Any:
        """Create async SQLAlchemy engine if it doesn't exist."""
        if self._engine is not None:
            return self._engine
        
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker
        except ImportError as e:
            raise ImportError(
                "Database storage requires sqlalchemy[asyncio]. "
                "Install with: pip install structure-d[storage]"
            ) from e
        
        # Ensure connection string uses asyncpg
        conn_str = self.connection_string
        if "+asyncpg" not in conn_str:
            conn_str = conn_str.replace("postgresql://", "postgresql+asyncpg://")
            conn_str = conn_str.replace("postgres://", "postgresql+asyncpg://")
        
        self._engine = create_async_engine(conn_str, echo=False)
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        return self._engine

    async def _ensure_table(self) -> Any:
        """Create table if it doesn't exist."""
        if self._initialized:
            return self._table
        
        await self._ensure_engine()
        
        try:
            from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, Text, Boolean
            from sqlalchemy.ext.asyncio import AsyncSession
        except ImportError as e:
            raise ImportError(
                "Database storage requires sqlalchemy. "
                "Install with: pip install structure-d[storage]"
            ) from e
        
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
        
        # Create tables asynchronously
        async with self._engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        
        self._initialized = True
        logger.info("database_table_created", table=f"{self.table_prefix}results")
        return self._table

    async def write(self, results: list[ExtractionResult]) -> int:
        """Insert *results* into the database. Returns count of rows inserted."""
        await self._ensure_table()
        
        if not results:
            return 0
        
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
        
        try:
            async with self._session_factory() as session:
                await session.execute(self._table.insert(), rows)
                await session.commit()
        except Exception as e:
            raise StorageError(
                f"Failed to write {len(rows)} results to database",
                storage_type="database",
                context={"error": str(e)},
            ) from e
        
        logger.info("database_written", count=len(rows))
        return len(rows)
    
    async def close(self) -> None:
        """Close the database connection pool."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._initialized = False