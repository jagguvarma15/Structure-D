"""Source connectors: local filesystem, S3, GCS, Azure, HTTP, SFTP, Google Drive, Dropbox."""

from __future__ import annotations

import abc
import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, AsyncIterator

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
        await asyncio.get_running_loop().run_in_executor(
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

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    async def list_files(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_running_loop()
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
        loop = asyncio.get_running_loop()
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


class GCSConnector(BaseConnector):
    """Download files from Google Cloud Storage. Requires ``google-cloud-storage``."""

    def __init__(self, bucket: str, prefix: str = "") -> None:
        self.bucket_name = bucket
        self.prefix = prefix
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import storage  # type: ignore[reportMissingImports]

                self._client = storage.Client()
            except ImportError as e:
                raise ImportError(
                    "google-cloud-storage is required for GCS connector. "
                    "Install with: pip install google-cloud-storage"
                ) from e
        return self._client

    async def list_files(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_running_loop()
        client = self._get_client()
        bucket = client.bucket(self.bucket_name)
        full_prefix = f"{self.prefix}/{prefix}".strip("/")

        def _list() -> list[str]:
            blobs = bucket.list_blobs(prefix=full_prefix)
            return [blob.name for blob in blobs]

        return await loop.run_in_executor(None, _list)

    async def download(self, key: str, dest: Path) -> Path:
        loop = asyncio.get_running_loop()
        client = self._get_client()
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(key)
        target = dest / Path(key).name

        def _download() -> None:
            blob.download_to_filename(str(target))

        await loop.run_in_executor(None, _download)
        return target


class AzureConnector(BaseConnector):
    """Download files from Azure Blob Storage. Requires ``azure-storage-blob``."""

    def __init__(self, account_name: str, container: str, prefix: str = "") -> None:
        self.account_name = account_name
        self.container_name = container
        self.prefix = prefix
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from azure.storage.blob import BlobServiceClient  # type: ignore[reportMissingImports]

                account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
                connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

                if connection_string:
                    self._client = BlobServiceClient.from_connection_string(connection_string)
                elif account_key:
                    account_url = f"https://{self.account_name}.blob.core.windows.net"
                    self._client = BlobServiceClient(account_url=account_url, credential=account_key)
                else:
                    raise ValueError(
                        "AZURE_STORAGE_ACCOUNT_KEY or AZURE_STORAGE_CONNECTION_STRING must be set"
                    )
            except ImportError as e:
                raise ImportError(
                    "azure-storage-blob is required for Azure connector. "
                    "Install with: pip install azure-storage-blob"
                ) from e
        return self._client

    async def list_files(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_running_loop()
        client = self._get_client()
        container = client.get_container_client(self.container_name)
        full_prefix = f"{self.prefix}/{prefix}".strip("/")

        def _list() -> list[str]:
            blobs = container.list_blobs(name_starts_with=full_prefix)
            return [blob.name for blob in blobs]

        return await loop.run_in_executor(None, _list)

    async def download(self, key: str, dest: Path) -> Path:
        loop = asyncio.get_running_loop()
        client = self._get_client()
        container = client.get_container_client(self.container_name)
        blob = container.get_blob_client(key)
        target = dest / Path(key).name

        def _download() -> None:
            with open(target, "wb") as f:
                blob.download_blob().readinto(f)

        await loop.run_in_executor(None, _download)
        return target


class SFTPConnector(BaseConnector):
    """Download files via SFTP. Requires ``paramiko``."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str | None = None,
        key_file: str | None = None,
        port: int = 22,
        base_path: str = "/",
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.key_file = key_file
        self.port = port
        self.base_path = base_path
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import paramiko  # type: ignore[reportMissingImports]

                transport = paramiko.Transport((self.host, self.port))
                if self.key_file:
                    key = paramiko.RSAKey.from_private_key_file(self.key_file)
                    transport.connect(username=self.username, pkey=key)
                else:
                    transport.connect(username=self.username, password=self.password)
                self._client = paramiko.SFTPClient.from_transport(transport)
            except ImportError as e:
                raise ImportError(
                    "paramiko is required for SFTP connector. Install with: pip install paramiko"
                ) from e
        return self._client

    async def list_files(self, prefix: str = "") -> list[str]:
        loop = asyncio.get_running_loop()
        client = self._get_client()
        full_path = f"{self.base_path}/{prefix}".strip("/")

        def _list() -> list[str]:
            files: list[str] = []
            try:
                items = client.listdir_attr(full_path)
                for item in items:
                    if item.st_mode & 0o100000:  # Regular file
                        files.append(f"{full_path}/{item.filename}".strip("/"))
                    elif item.st_mode & 0o040000:  # Directory
                        # Recursively list subdirectories
                        sub_files = self._list_recursive(client, f"{full_path}/{item.filename}")
                        files.extend(sub_files)
            except FileNotFoundError:
                pass
            return files

        return await loop.run_in_executor(None, _list)

    def _list_recursive(self, client: Any, path: str) -> list[str]:
        """Recursively list files in a directory."""
        files: list[str] = []
        try:
            items = client.listdir_attr(path)
            for item in items:
                full_path = f"{path}/{item.filename}".strip("/")
                if item.st_mode & 0o100000:  # Regular file
                    files.append(full_path)
                elif item.st_mode & 0o040000:  # Directory
                    sub_files = self._list_recursive(client, full_path)
                    files.extend(sub_files)
        except (FileNotFoundError, PermissionError):
            pass
        return files

    async def download(self, key: str, dest: Path) -> Path:
        loop = asyncio.get_running_loop()
        client = self._get_client()
        target = dest / Path(key).name

        def _download() -> None:
            client.get(key, str(target))

        await loop.run_in_executor(None, _download)
        return target


# ── Factory ───────────────────────────────────────────────────────────────────

_CONNECTORS: dict[str, type[BaseConnector]] = {
    "local": LocalConnector,
    "s3": S3Connector,
    "gcs": GCSConnector,
    "azure": AzureConnector,
    "sftp": SFTPConnector,
    "http": HTTPConnector,
}


def get_connector(name: str, **kwargs: object) -> BaseConnector:
    """Instantiate a connector by name."""
    cls = _CONNECTORS.get(name)
    if cls is None:
        raise ValueError(f"Unknown connector: {name!r}. Available: {list(_CONNECTORS)}")
    return cls(**kwargs)  # type: ignore[arg-type]
