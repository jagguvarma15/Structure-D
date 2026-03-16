"""Pydantic models for API request/response payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from structure_d.schemas.base import TaskType


class ExtractRequest(BaseModel):
    """Request body for the /extract endpoint."""

    task: TaskType = TaskType.EXTRACTION
    model: str | None = None
    parser: str | None = None
    schema_name: str = "generic"
    save_format: str | None = None  # jsonl | csv


class ExtractResponse(BaseModel):
    """Response for the /extract endpoint."""

    document_id: str
    filename: str
    detected_format: str
    schema_used: str
    chunks: int
    results: list[dict[str, Any]]
    valid_count: int
    total_count: int
    elapsed_ms: float


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"


class ModelsResponse(BaseModel):
    models: list[dict[str, Any]]


class SchemasResponse(BaseModel):
    schemas: list[dict[str, str]]


class FormatsResponse(BaseModel):
    formats: dict[str, list[str]]
