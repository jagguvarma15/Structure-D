"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from structure_d.config import get_settings
from structure_d.monitoring.logging import setup_logging


def create_app():  # noqa: ANN201
    """Create and configure the FastAPI application."""
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as e:
        raise ImportError(
            "FastAPI is required for the API service. "
            "Install with: pip install structure-d[api]"
        ) from e

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging()
        yield

    app = FastAPI(
        title="Structure-D API",
        description="Convert unstructured documents to structured data.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from structure_d.api.routes import router

    app.include_router(router, prefix="/api/v1")

    return app
