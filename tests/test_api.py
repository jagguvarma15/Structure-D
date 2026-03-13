"""Tests for the FastAPI endpoints (health, schemas, formats)."""

from __future__ import annotations

import pytest

try:
    from httpx import ASGITransport, AsyncClient

    from structure_d.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi / httpx not installed")


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_health(client: AsyncClient):
    """GET /api/v1/health should return 200 with status=ok."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_schemas(client: AsyncClient):
    """GET /api/v1/schemas should list built-in schema names."""
    resp = await client.get("/api/v1/schemas")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()["schemas"]}
    assert "key_value" in names
    assert "table" in names
    assert "generic" in names


async def test_formats(client: AsyncClient):
    """GET /api/v1/formats should return a mapping of format → extensions."""
    resp = await client.get("/api/v1/formats")
    assert resp.status_code == 200
    formats = resp.json()["formats"]
    assert ".pdf" in formats.get("pdf", [])
    assert ".html" in formats.get("html", [])


async def test_models(client: AsyncClient):
    """GET /api/v1/models should return a non-empty model list."""
    resp = await client.get("/api/v1/models")
    assert resp.status_code == 200
    assert isinstance(resp.json()["models"], list)
