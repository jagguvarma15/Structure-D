"""Destination writers: Snowflake, BigQuery, Redshift, MySQL, MSSQL, Oracle."""

from __future__ import annotations

import abc
import asyncio
import os
from typing import Any

import structlog

from structure_d.exceptions import StorageError

logger = structlog.get_logger(__name__)


class BaseDestination(abc.ABC):
    """Interface for destination writers."""

    @abc.abstractmethod
    async def write(self, data: list[dict[str, Any]], table: str, schema: str | None = None) -> int:
        """
        Write structured data to the destination.

        Args:
            data: List of dictionaries representing rows
            table: Table name
            schema: Optional schema/database name

        Returns:
            Number of rows written
        """

    @abc.abstractmethod
    async def create_table_if_not_exists(
        self, table: str, columns: dict[str, str], schema: str | None = None
    ) -> None:
        """
        Create a table if it doesn't exist.

        Args:
            table: Table name
            columns: Dictionary mapping column names to SQL types
            schema: Optional schema/database name
        """


class SnowflakeWriter(BaseDestination):
    """Write to Snowflake. Requires ``snowflake-connector-python``."""

    def __init__(
        self,
        account: str | None = None,
        user: str | None = None,
        password: str | None = None,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
    ) -> None:
        self.account = account or os.getenv("SNOWFLAKE_ACCOUNT")
        self.user = user or os.getenv("SNOWFLAKE_USER")
        self.password = password or os.getenv("SNOWFLAKE_PASSWORD")
        self.warehouse = warehouse or os.getenv("SNOWFLAKE_WAREHOUSE")
        self.database = database or os.getenv("SNOWFLAKE_DATABASE")
        self.schema = schema or os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
        self._connection = None

    def _get_connection(self) -> Any:
        if self._connection is None:
            try:
                import snowflake.connector  # type: ignore[reportMissingImports]

                self._connection = snowflake.connector.connect(
                    account=self.account,
                    user=self.user,
                    password=self.password,
                    warehouse=self.warehouse,
                    database=self.database,
                    schema=self.schema,
                )
            except ImportError as e:
                raise ImportError(
                    "snowflake-connector-python is required for Snowflake. "
                    "Install with: pip install snowflake-connector-python"
                ) from e
        return self._connection

    async def create_table_if_not_exists(
        self, table: str, columns: dict[str, str], schema: str | None = None
    ) -> None:
        conn = self._get_connection()
        schema_name = schema or self.schema
        full_table = f"{schema_name}.{table}" if schema_name else table

        # Map Python types to Snowflake types
        type_map = {
            "str": "VARCHAR",
            "int": "NUMBER",
            "float": "FLOAT",
            "bool": "BOOLEAN",
            "datetime": "TIMESTAMP_NTZ",
        }

        col_defs = ", ".join(
            f"{col} {type_map.get(col_type, 'VARCHAR')}" for col, col_type in columns.items()
        )
        sql = f"CREATE TABLE IF NOT EXISTS {full_table} ({col_defs})"

        def _execute() -> None:
            cursor = conn.cursor()
            cursor.execute(sql)
            cursor.close()

        await asyncio.get_running_loop().run_in_executor(None, _execute)

    async def write(self, data: list[dict[str, Any]], table: str, schema: str | None = None) -> int:
        if not data:
            return 0

        conn = self._get_connection()
        schema_name = schema or self.schema
        full_table = f"{schema_name}.{table}" if schema_name else table

        # Infer columns from first row
        columns = list(data[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        sql = f"INSERT INTO {full_table} ({col_names}) VALUES ({placeholders})"

        def _write() -> int:
            cursor = conn.cursor()
            rows = [[row.get(col) for col in columns] for row in data]
            cursor.executemany(sql, rows)
            cursor.close()
            return len(rows)

        return await asyncio.get_running_loop().run_in_executor(None, _write)


class BigQueryWriter(BaseDestination):
    """Write to Google BigQuery. Requires ``google-cloud-bigquery``."""

    def __init__(self, project: str | None = None, dataset: str | None = None) -> None:
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset = dataset or os.getenv("BIGQUERY_DATASET")
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import bigquery  # type: ignore[reportMissingImports]

                self._client = bigquery.Client(project=self.project)
            except ImportError as e:
                raise ImportError(
                    "google-cloud-bigquery is required for BigQuery. "
                    "Install with: pip install google-cloud-bigquery"
                ) from e
        return self._client

    async def create_table_if_not_exists(
        self, table: str, columns: dict[str, str], schema: str | None = None
    ) -> None:
        try:
            from google.cloud import bigquery  # type: ignore[reportMissingImports]
        except ImportError as e:
            raise ImportError(
                "google-cloud-bigquery is required for BigQuery. "
                "Install with: pip install google-cloud-bigquery"
            ) from e

        client = self._get_client()
        dataset_name = schema or self.dataset
        table_id = f"{self.project}.{dataset_name}.{table}"

        # Map Python types to BigQuery types
        type_map = {
            "str": "STRING",
            "int": "INT64",
            "float": "FLOAT64",
            "bool": "BOOL",
            "datetime": "TIMESTAMP",
        }

        schema_fields = [
            bigquery.SchemaField(col, type_map.get(col_type, "STRING"))
            for col, col_type in columns.items()
        ]

        def _create() -> None:
            table_obj = bigquery.Table(table_id, schema=schema_fields)
            client.create_table(table_obj, exists_ok=True)

        await asyncio.get_running_loop().run_in_executor(None, _create)

    async def write(self, data: list[dict[str, Any]], table: str, schema: str | None = None) -> int:
        if not data:
            return 0

        client = self._get_client()
        dataset_name = schema or self.dataset
        table_id = f"{self.project}.{dataset_name}.{table}"

        def _write() -> int:
            errors = client.insert_rows_json(table_id, data)
            if errors:
                raise StorageError(f"BigQuery write errors: {errors}")
            return len(data)

        return await asyncio.get_running_loop().run_in_executor(None, _write)


class MySQLWriter(BaseDestination):
    """Write to MySQL/MariaDB. Requires ``aiomysql`` or ``asyncmy``."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user or os.getenv("MYSQL_USER", "root")
        self.password = password or os.getenv("MYSQL_PASSWORD", "")
        self.database = database or os.getenv("MYSQL_DATABASE")

    async def create_table_if_not_exists(
        self, table: str, columns: dict[str, str], schema: str | None = None
    ) -> None:
        try:
            import asyncmy  # type: ignore[reportMissingImports]
        except ImportError:
            raise ImportError(
                "asyncmy is required for MySQL. Install with: pip install asyncmy"
            ) from None

        db = schema or self.database
        if not db:
            raise ValueError("Database name must be provided")

        # Map Python types to MySQL types
        type_map = {
            "str": "TEXT",
            "int": "INT",
            "float": "DOUBLE",
            "bool": "BOOLEAN",
            "datetime": "DATETIME",
        }

        col_defs = ", ".join(
            f"`{col}` {type_map.get(col_type, 'TEXT')}" for col, col_type in columns.items()
        )
        sql = f"CREATE TABLE IF NOT EXISTS `{db}`.`{table}` ({col_defs})"

        conn = await asyncmy.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=db,
        )
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(sql)
            await conn.commit()
        finally:
            conn.close()

    async def write(self, data: list[dict[str, Any]], table: str, schema: str | None = None) -> int:
        try:
            import asyncmy  # type: ignore[reportMissingImports]
        except ImportError:
            raise ImportError(
                "asyncmy is required for MySQL. Install with: pip install asyncmy"
            ) from None

        if not data:
            return 0

        db = schema or self.database
        if not db:
            raise ValueError("Database name must be provided")

        columns = list(data[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        col_names = ", ".join(f"`{col}`" for col in columns)
        sql = f"INSERT INTO `{db}`.`{table}` ({col_names}) VALUES ({placeholders})"

        conn = await asyncmy.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=db,
        )
        try:
            rows = [[row.get(col) for col in columns] for row in data]
            async with conn.cursor() as cursor:
                await cursor.executemany(sql, rows)
            await conn.commit()
            return len(rows)
        finally:
            conn.close()


class RedshiftWriter(BaseDestination):
    """Write to Amazon Redshift. Uses ``asyncpg`` (PostgreSQL-compatible)."""

    def __init__(
        self,
        host: str,
        port: int = 5439,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user or os.getenv("REDSHIFT_USER")
        self.password = password or os.getenv("REDSHIFT_PASSWORD")
        self.database = database or os.getenv("REDSHIFT_DATABASE")
        self._connection_string = (
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        )

    async def create_table_if_not_exists(
        self, table: str, columns: dict[str, str], schema: str | None = None
    ) -> None:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine  # type: ignore[reportMissingImports]
            from sqlalchemy import text  # type: ignore[reportMissingImports]

            engine = create_async_engine(self._connection_string)
        except ImportError:
            raise ImportError(
                "sqlalchemy and asyncpg are required for Redshift. "
                "Install with: pip install sqlalchemy asyncpg"
            ) from None

        schema_name = schema or "public"
        type_map = {
            "str": "VARCHAR(65535)",
            "int": "INTEGER",
            "float": "DOUBLE PRECISION",
            "bool": "BOOLEAN",
            "datetime": "TIMESTAMP",
        }

        col_defs = ", ".join(
            f'"{col}" {type_map.get(col_type, "VARCHAR(65535)")}' for col, col_type in columns.items()
        )
        sql = f'CREATE TABLE IF NOT EXISTS "{schema_name}"."{table}" ({col_defs})'

        async with engine.begin() as conn:
            await conn.execute(text(sql))

    async def write(self, data: list[dict[str, Any]], table: str, schema: str | None = None) -> int:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine  # type: ignore[reportMissingImports]
            from sqlalchemy import text  # type: ignore[reportMissingImports]

            engine = create_async_engine(self._connection_string)
        except ImportError:
            raise ImportError(
                "sqlalchemy and asyncpg are required for Redshift. "
                "Install with: pip install sqlalchemy asyncpg"
            ) from None

        if not data:
            return 0

        schema_name = schema or "public"
        columns = list(data[0].keys())
        col_names = ", ".join(f'"{col}"' for col in columns)
        placeholders = ", ".join([f":{col}" for col in columns])

        sql = f'INSERT INTO "{schema_name}"."{table}" ({col_names}) VALUES ({placeholders})'

        async with engine.begin() as conn:
            rows = [dict(row) for row in data]
            await conn.execute(text(sql), rows)
            return len(rows)


# ── Factory ───────────────────────────────────────────────────────────────────

_DESTINATIONS: dict[str, type[BaseDestination]] = {
    "snowflake": SnowflakeWriter,
    "bigquery": BigQueryWriter,
    "mysql": MySQLWriter,
    "redshift": RedshiftWriter,
}


def get_destination(name: str, **kwargs: object) -> BaseDestination:
    """Instantiate a destination by name."""
    cls = _DESTINATIONS.get(name)
    if cls is None:
        raise ValueError(f"Unknown destination: {name!r}. Available: {list(_DESTINATIONS)}")
    return cls(**kwargs)  # type: ignore[arg-type]
