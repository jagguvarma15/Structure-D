"""API route definitions."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _get_router():  # noqa: ANN202
    """Lazy import to avoid hard dependency on fastapi."""
    from fastapi import APIRouter, File, Form, HTTPException, UploadFile

    from structure_d.api.models import (
        ExtractRequest,
        ExtractResponse,
        FormatsResponse,
        HealthResponse,
        ModelsResponse,
        SchemasResponse,
    )
    from structure_d.config import get_settings
    from structure_d.schemas.base import TaskType, detect_format

    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @router.get("/models", response_model=ModelsResponse)
    async def list_models() -> ModelsResponse:
        from structure_d.models.registry import ModelRegistry

        settings = get_settings()
        registry = ModelRegistry.from_yaml(settings.models.registry_path)
        models = [m.model_dump() for m in registry.list_models()]
        return ModelsResponse(models=models)

    @router.get("/schemas", response_model=SchemasResponse)
    async def list_schemas() -> SchemasResponse:
        from structure_d.schemas.generic import BUILTIN_SCHEMAS

        return SchemasResponse(
            schemas=[
                {"name": name, "description": (cls.__doc__ or "").strip().split("\n")[0]}
                for name, cls in BUILTIN_SCHEMAS.items()
            ]
        )

    @router.get("/formats", response_model=FormatsResponse)
    async def list_formats() -> FormatsResponse:
        from structure_d.schemas.base import _EXT_TO_FORMAT

        by_format: dict[str, list[str]] = {}
        for ext, fmt in _EXT_TO_FORMAT.items():
            by_format.setdefault(fmt.value, []).append(ext)
        return FormatsResponse(formats=by_format)

    @router.post("/extract", response_model=ExtractResponse)
    async def extract(
        file: UploadFile = File(...),
        task: str = Form("extraction"),
        model: str | None = Form(None),
        parser: str | None = Form(None),
        schema_name: str = Form("generic"),
        save_format: str | None = Form(None),
    ) -> ExtractResponse:
        """Upload a document (any format) and receive structured extraction results."""
        from structure_d.pipeline import Pipeline
        from structure_d.schemas.generic import BUILTIN_SCHEMAS, GenericExtraction

        t0 = time.monotonic()

        # Resolve schema by name
        schema_cls = BUILTIN_SCHEMAS.get(schema_name, GenericExtraction)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / (file.filename or "upload")
            content = await file.read()
            tmp_path.write_bytes(content)

            detected = detect_format(tmp_path.suffix)

            pipeline = Pipeline(
                schema_cls=schema_cls,
                task=TaskType(task),
            )
            results = await pipeline.run(
                tmp_path,
                parser_name=parser,
                model=model,
                save_format=save_format,
            )

        elapsed = (time.monotonic() - t0) * 1000
        valid_count = sum(1 for r in results if r.is_valid)
        doc_id = results[0].document_id if results else ""

        return ExtractResponse(
            document_id=doc_id,
            filename=file.filename or "",
            detected_format=detected.value,
            schema_used=schema_name,
            chunks=len(results),
            results=[
                {
                    "chunk_id": r.chunk_id,
                    "source_format": r.source_format.value,
                    "structured_output": r.structured_output,
                    "is_valid": r.is_valid,
                    "validation_errors": r.validation_errors,
                    "latency_ms": r.latency_ms,
                }
                for r in results
            ],
            valid_count=valid_count,
            total_count=len(results),
            elapsed_ms=round(elapsed, 1),
        )

    return router


# Module-level router instance (lazily built)
try:
    router = _get_router()
except ImportError:
    # FastAPI not installed – provide a stub
    router = None  # type: ignore[assignment]
