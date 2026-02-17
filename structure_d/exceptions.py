"""Custom exception types for Structure-D."""

from __future__ import annotations


class StructureDError(Exception):
    """Base exception for all Structure-D errors."""

    def __init__(self, message: str, *, context: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


class ParserError(StructureDError):
    """Raised when document parsing fails."""

    def __init__(
        self,
        message: str,
        *,
        file_path: str | None = None,
        parser_name: str | None = None,
        format: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.file_path = file_path
        self.parser_name = parser_name
        self.format = format


class ValidationError(StructureDError):
    """Raised when schema validation fails after all retries."""

    def __init__(
        self,
        message: str,
        *,
        schema_name: str | None = None,
        validation_errors: list[str] | None = None,
        raw_output: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.schema_name = schema_name
        self.validation_errors = validation_errors or []
        self.raw_output = raw_output


class InferenceError(StructureDError):
    """Raised when LLM inference fails."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.model = model
        self.status_code = status_code
        self.response_body = response_body


class ConfigurationError(StructureDError):
    """Raised when configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        *,
        config_key: str | None = None,
        config_path: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.config_key = config_key
        self.config_path = config_path


class ModelRoutingError(StructureDError):
    """Raised when model routing fails (no suitable model found)."""

    def __init__(
        self,
        message: str,
        *,
        task: str | None = None,
        available_models: list[str] | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.task = task
        self.available_models = available_models or []


class StorageError(StructureDError):
    """Raised when storage operations fail."""

    def __init__(
        self,
        message: str,
        *,
        storage_type: str | None = None,
        file_path: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.storage_type = storage_type
        self.file_path = file_path


class RetrievalError(StructureDError):
    """Raised when vector store or RAG operations fail."""

    def __init__(
        self,
        message: str,
        *,
        vector_store: str | None = None,
        operation: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.vector_store = vector_store
        self.operation = operation
