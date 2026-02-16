"""Document ingestion and parsing layer."""

from structure_d.ingestion.base import BaseParser, ParserRegistry
from structure_d.ingestion.connectors import LocalConnector, get_connector
from structure_d.ingestion.manager import IngestionManager

__all__ = [
    "BaseParser",
    "IngestionManager",
    "LocalConnector",
    "ParserRegistry",
    "get_connector",
]
