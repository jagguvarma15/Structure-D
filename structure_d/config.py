"""
Centralised configuration management.

Loads settings from YAML files and environment variables using pydantic-settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from structure_d.exceptions import ConfigurationError


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

    @field_validator("registry_path")
    @classmethod
    def validate_registry_path(cls, v: str) -> str:
        """Validate that models registry file exists."""
        path = Path(v)
        if not path.exists():
            raise ConfigurationError(
                f"Models registry file not found: {v}",
                config_key="models.registry_path",
                config_path=str(path),
            )
        return v


class VLLMConfig(BaseModel):
    api_base: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    gpu_memory_utilization: float = 0.90
    max_model_len: int = 8192
    max_num_seqs: int = 256
    structured_output_backend: str = "auto"
    timeout_seconds: int = 120
    max_retries: int = 3

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, v: str) -> str:
        """Validate that api_base is a valid URL."""
        try:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Invalid URL format: {v}")
            return v
        except Exception as e:
            raise ConfigurationError(
                f"Invalid vLLM API base URL: {v}",
                config_key="inference.vllm.api_base",
            ) from e

    @field_validator("gpu_memory_utilization")
    @classmethod
    def validate_gpu_memory(cls, v: float) -> float:
        """Validate GPU memory utilization is between 0 and 1."""
        if not 0 < v <= 1:
            raise ConfigurationError(
                f"GPU memory utilization must be between 0 and 1, got {v}",
                config_key="inference.vllm.gpu_memory_utilization",
            )
        return v

    @field_validator("structured_output_backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate structured output backend."""
        valid = ["auto", "xgrammar", "guidance", "outlines", "lm-format-enforcer"]
        if v not in valid:
            raise ConfigurationError(
                f"Invalid structured_output_backend: {v}. Must be one of {valid}",
                config_key="inference.vllm.structured_output_backend",
            )
        return v


class BatchConfig(BaseModel):
    max_batch_size: int = 32
    flush_interval_seconds: float = 1.0
    max_concurrent_files: int = 4


class OpenAIProviderConfig(BaseModel):
    model: str = "gpt-4o"
    api_key: str | None = None
    base_url: str | None = None


class AnthropicProviderConfig(BaseModel):
    model: str = "claude-3-5-sonnet-20241022"
    api_key: str | None = None


class GeminiProviderConfig(BaseModel):
    model: str = "gemini-1.5-pro"
    api_key: str | None = None


class OllamaProviderConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"


class ProviderConfig(BaseModel):
    """Configuration for LLM providers."""

    provider: Literal["vllm", "openai", "anthropic", "gemini", "ollama"] = "vllm"
    # When set, the named provider is used as a transparent fallback whenever
    # the primary provider raises an InferenceError (e.g. vLLM not reachable).
    fallback_provider: Literal["vllm", "openai", "anthropic", "gemini", "ollama"] | None = None
    vllm: VLLMConfig = Field(default_factory=VLLMConfig)
    openai: OpenAIProviderConfig = Field(default_factory=OpenAIProviderConfig)
    anthropic: AnthropicProviderConfig = Field(default_factory=AnthropicProviderConfig)
    gemini: GeminiProviderConfig = Field(default_factory=GeminiProviderConfig)
    ollama: OllamaProviderConfig = Field(default_factory=OllamaProviderConfig)


class InferenceConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
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
    default_format: Literal["jsonl", "csv", "markdown", "database"] = "jsonl"
    output_directory: str = "./output"
    jsonl: JSONLConfig = Field(default_factory=JSONLConfig)
    csv: CSVConfig = Field(default_factory=CSVConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @field_validator("output_directory")
    @classmethod
    def validate_output_directory(cls, v: str) -> str:
        """Ensure output directory exists or can be created."""
        path = Path(v)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ConfigurationError(
                f"Cannot create output directory: {v}",
                config_key="storage.output_directory",
            ) from e
        return v


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

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        """Perform cross-field validation."""
        # Validate that if retrieval is enabled, vector store config is valid
        if self.retrieval.enabled:
            if self.retrieval.vector_store == "pgvector":
                conn_str = self.retrieval.pgvector.connection_string
                if not conn_str or conn_str == "postgresql+asyncpg://user:pass@localhost:5432/structure_d":
                    raise ConfigurationError(
                        "PGVector connection string must be configured when using pgvector",
                        config_key="retrieval.pgvector.connection_string",
                    )
        return self


def load_settings(config_path: str | Path | None = None) -> Settings:
    """
    Load settings from a YAML file, overlaid with environment variables.
    
    Raises ConfigurationError if validation fails.
    """
    data: dict[str, Any] = {}
    if config_path is None:
        config_path = os.getenv("SD_CONFIG_PATH", "configs/default.yaml")
    path = Path(config_path)
    if path.exists():
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load config file: {path}",
                config_path=str(path),
            ) from e
    try:
        return Settings(**data)
    except Exception as e:
        if isinstance(e, ConfigurationError):
            raise
        raise ConfigurationError(
            f"Configuration validation failed: {e}",
            config_path=str(path),
        ) from e


# Module-level singleton (lazy)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached settings singleton."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = load_settings()
    return _settings
