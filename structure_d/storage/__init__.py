"""Output storage: JSONL, CSV, database, and cloud destinations."""

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

__all__ = [
    "BaseDestination",
    "BigQueryWriter",
    "CSVWriter",
    "DatabaseWriter",
    "JSONLWriter",
    "MySQLWriter",
    "RedshiftWriter",
    "SnowflakeWriter",
    "get_destination",
]
