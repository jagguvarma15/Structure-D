"""Output storage: JSONL, CSV, Markdown, database, and cloud destinations."""

from structure_d.storage.csv_store import CSVWriter
from structure_d.storage.database import DatabaseWriter
from structure_d.storage.destinations import (
    BaseDestination,
    BigQueryWriter,
    MySQLWriter,
    RedshiftWriter,
    SnowflakeWriter,
    get_destination,
)
from structure_d.storage.jsonl import JSONLWriter
from structure_d.storage.markdown import MarkdownWriter

__all__ = [
    "BaseDestination",
    "BigQueryWriter",
    "CSVWriter",
    "DatabaseWriter",
    "JSONLWriter",
    "MarkdownWriter",
    "MySQLWriter",
    "RedshiftWriter",
    "SnowflakeWriter",
    "get_destination",
]
