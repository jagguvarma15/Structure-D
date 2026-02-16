"""
Centralised configuration management.

Loads settings from YAML files and environment variables using pydantic-settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ── Sub-models ────────────────────────────────────────────────────────────────


class ConnectorConfig(BaseModel):
    enabled: bool = False
    bucket: str = ""
    region: str = "us-east-1"


class IngestionConfig(BaseModel):
    default_parser: Literal["auto", "pymupdf", "pdfplumber", "unstructured", "docling"] = "auto"
    ocr_enabled: bool = True
    ocr_engine: Literal["tesseract", "easyocr"] = "tesseract"
    ocr_languages: list[str] = Field(default_factory=lambda: ["eng"])
    max_file_size_mb: int = 200
    supported_extensions: list[str] = Field(
        default_factory=lambda: [
            ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
            ".html", ".htm", ".docx", ".xlsx", ".pptx",
            ".eml", ".txt", ".csv", ".md",
        ]
    )
    connectors: dict[str, ConnectorConfig] = Field(default_factory=dict)


class ChunkingConfig(BaseModel):
    strategy: Literal["fixed", "sentence", "semantic", "heading"] = "semantic"
    max_tokens: int = 1024
    overlap_tokens: int = 128
    heading_level: int = 2


class PreprocessingConfig(BaseModel):
    normalize_unicode: bool = True
    strip_boilerplate: bool = True
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)


class ModelsConfig(BaseModel):
    registry_path: str = "configs/models.yaml"
    default_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    embedding_model: str = "intfloat/e5-large-v2"


class VLLMConfig(BaseModel):
    api_base: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    gpu_memory_utilization: float = 0.90
    max_model_len: int = 8192
    max_num_seqs: int = 256
    structured_output_backend: str = "auto"
    timeout_seconds: int = 120
    max_retries: int = 3


class BatchConfig(BaseModel):
    max_batch_size: int = 32
    flush_interval_seconds: float = 1.0


class InferenceConfig(BaseModel):
    vllm: VLLMConfig = Field(default_factory=VLLMConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)


class ValidationConfig(BaseModel):
    strict_mode: bool = True
    max_retries: int = 3
    retry_with_refined_prompt: bool = True
    fallback_to_regex: bool = True


class ChromaConfig(BaseModel):
    persist_directory: str = "./data/chroma"


class PGVectorConfig(BaseModel):
    connection_string: str = "postgresql+asyncpg://user:pass@localhost:5432/structure_d"


class MilvusConfig(BaseModel):
    uri: str = "http://localhost:19530"


class RetrievalConfig(BaseModel):
    enabled: bool = False
    framework: Literal["langchain", "llama_index", "haystack"] = "langchain"
    vector_store: Literal["chroma", "pgvector", "milvus", "faiss"] = "chroma"
    top_k: int = 5
    similarity_threshold: float = 0.75
    embedding_dimension: int = 1024
    chroma: ChromaConfig = Field(default_factory=ChromaConfig)
    pgvector: PGVectorConfig = Field(default_factory=PGVectorConfig)
    milvus: MilvusConfig = Field(default_factory=MilvusConfig)


class JSONLConfig(BaseModel):
    indent: int | None = None


class CSVConfig(BaseModel):
    delimiter: str = ","
    quoting: str = "minimal"


class DatabaseConfig(BaseModel):
    connection_string: str = "postgresql+asyncpg://user:pass@localhost:5432/structure_d"
    table_prefix: str = "sd_"


class StorageConfig(BaseModel):
    default_format: Literal["jsonl", "csv", "database"] = "jsonl"
    output_directory: str = "./output"
    jsonl: JSONLConfig = Field(default_factory=JSONLConfig)
    csv: CSVConfig = Field(default_factory=CSVConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    max_upload_size_mb: int = 200


class PrometheusConfig(BaseModel):
    enabled: bool = True
    port: int = 9090


class LoggingConfig(BaseModel):
    structured: bool = True
    file: str = "./logs/structure_d.log"
    max_size_mb: int = 100
    backup_count: int = 5


class MonitoringConfig(BaseModel):
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# ── Root configuration ────────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Root application settings, loadable from YAML + env vars."""

    project_name: str = "structure-d"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    model_config = {"env_prefix": "SD_", "env_nested_delimiter": "__"}


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file, overlaid with environment variables."""
    data: dict[str, Any] = {}
    if config_path is None:
        config_path = os.getenv("SD_CONFIG_PATH", "configs/default.yaml")
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    return Settings(**data)


# Module-level singleton (lazy)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached settings singleton."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = load_settings()
    return _settings
