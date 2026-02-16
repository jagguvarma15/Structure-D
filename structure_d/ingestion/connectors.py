"""Source connectors: local filesystem, S3, GCS, HTTP."""

from __future__ import annotations

import abc
import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import AsyncIterator

import structlog

logger = structlog.get_logger(__name__)


class BaseConnector(abc.ABC):
    """Interface for source connectors."""

    @abc.abstractmethod
    async def list_files(self, prefix: str = "") -> list[str]:
        """Return a list of file paths / keys under *prefix*."""

    @abc.abstractmethod
    async def download(self, key: str, dest: Path) -> Path:
        """Download *key* to *dest* and return the local path."""

    async def iter_files(self, prefix: str = "") -> AsyncIterator[str]:
        """Yield file keys one by one (default: materialise list)."""
        for key in await self.list_files(prefix):
            yield key


class LocalConnector(BaseConnector):
    """Reads files from the local filesystem."""

    def __init__(self, base_dir: str | Path = ".") -> None:
        self.base_dir = Path(base_dir)

    async def list_files(self, prefix: str = "") -> list[str]:
        root = self.base_dir / prefix
        if not root.exists():
            return []
        return sorted(
            str(p.relative_to(self.base_dir))
            for p in root.rglob("*")
            if p.is_file()
        )

    async def download(self, key: str, dest: Path) -> Path:
        src = self.base_dir / key
        if not src.exists():
            raise FileNotFoundError(f"File not found: {src}")
        target = dest / src.name
        await asyncio.get_event_loop().run_in_executor(
            None, shutil.copy2, str(src), str(target)
        )
        return target


class S3Connector(BaseConnector):
    """Download files from an S3 bucket.  Requires ``boto3``."""

    def __init__(self, bucket: str, region: str = "us-east-1", prefix: str = "") -> None:
        self.bucket = bucket
        self.region = region
        self.prefix = prefix
        self._client = None

    def _get_client(self):  # noqa: ANN202
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    async def list_files(self, prefix: str = "") -> list[str]:
        import boto3

        loop = asyncio.get_event_loop()
        s3 = self._get_client()
        full_prefix = f"{self.prefix}/{prefix}".strip("/")

        def _list() -> list[str]:
            paginator = s3.get_paginator("list_objects_v2")
            keys: list[str] = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
            return keys

        return await loop.run_in_executor(None, _list)

    async def download(self, key: str, dest: Path) -> Path:
        loop = asyncio.get_event_loop()
        s3 = self._get_client()
        target = dest / Path(key).name

        def _download() -> None:
            s3.download_file(self.bucket, key, str(target))

        await loop.run_in_executor(None, _download)
        return target


class HTTPConnector(BaseConnector):
    """Download a single file from a URL."""

    async def list_files(self, prefix: str = "") -> list[str]:
        # A URL connector typically receives URLs directly
        return [prefix] if prefix else []

    async def download(self, key: str, dest: Path) -> Path:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(key)
            resp.raise_for_status()
            # Infer filename from URL or Content-Disposition
            filename = Path(key.split("?")[0]).name or "download"
            target = dest / filename
            target.write_bytes(resp.content)
        return target


# ── Factory ───────────────────────────────────────────────────────────────────

_CONNECTORS: dict[str, type[BaseConnector]] = {
    "local": LocalConnector,
    "s3": S3Connector,
    "http": HTTPConnector,
}


def get_connector(name: str, **kwargs: object) -> BaseConnector:
    """Instantiate a connector by name."""
    cls = _CONNECTORS.get(name)
    if cls is None:
        raise ValueError(f"Unknown connector: {name!r}. Available: {list(_CONNECTORS)}")
    return cls(**kwargs)  # type: ignore[arg-type]
