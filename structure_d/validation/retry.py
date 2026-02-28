"""Retry / fallback logic for validation failures."""

from __future__ import annotations

import json
from typing import Type

import structlog
from pydantic import BaseModel

from structure_d.config import get_settings
from structure_d.exceptions import InferenceError
from structure_d.inference.providers import BaseLLMProvider, VLLMProvider
from structure_d.inference.structured_output import StructuredOutputBuilder
from structure_d.schemas.base import ExtractionResult, TaskType
from structure_d.validation.validator import SchemaValidator

logger = structlog.get_logger(__name__)


class RetryHandler:
    """
    Validate extraction results and retry on failure.

    Flow
    ----
    1. If the result is already valid (``is_valid=True``), return immediately.
       Providers that use constrained decoding or native structured outputs
       guarantee validity, so re-validation is redundant.
    2. If invalid, call ``provider.generate()`` with a *refined prompt* that
       includes the original text and the error descriptions, giving the model
       a chance to self-correct.
    3. Repeat up to ``max_retries`` times.

    The :class:`~structure_d.validation.validator.SchemaValidator` is kept as
    a utility for callers that need raw-string validation outside this flow.
    """

    def __init__(
        self,
        schema_cls: Type[BaseModel],
        task: TaskType = TaskType.EXTRACTION,
        provider: BaseLLMProvider | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.schema_cls = schema_cls
        self.task = task
        self.validator = SchemaValidator(schema_cls)
        self.provider = provider or VLLMProvider()
        self.max_retries = max_retries or settings.validation.max_retries
        self.retry_with_prompt = settings.validation.retry_with_refined_prompt
        self.builder = StructuredOutputBuilder(schema_cls=schema_cls, task=task)

    async def validate_and_retry(
        self,
        result: ExtractionResult,
        original_text: str,
        model: str | None = None,
    ) -> ExtractionResult:
        """
        Ensure *result* is valid, retrying via the provider if it is not.

        Mutates and returns the same :class:`ExtractionResult` instance.
        """
        # Fast path: provider already validated the output.
        if result.is_valid:
            return result

        errors = result.validation_errors or ["Provider returned invalid or empty output"]

        if not self.retry_with_prompt:
            result.validation_errors = errors
            return result

        for attempt in range(1, self.max_retries + 1):
            logger.info(
                "validation_retry",
                attempt=attempt,
                errors=errors,
                chunk_id=result.chunk_id,
            )

            refined_prompt = self._build_refined_user_prompt(original_text, errors)
            system_prompt = self.builder.build_system_prompt()

            try:
                pr = await self.provider.generate(
                    prompt=refined_prompt,
                    schema=self.schema_cls,
                    system_prompt=system_prompt,
                    model=model,
                )
                result.raw_output = pr.raw_text or json.dumps(pr.output.model_dump())
                result.structured_output = pr.output.model_dump()
                result.model_used = pr.model_used
                result.is_valid = True
                result.validation_errors = []
                return result
            except InferenceError as exc:
                errors = [str(exc)]
                logger.warning(
                    "validation_retry_failed",
                    attempt=attempt,
                    error=str(exc),
                    chunk_id=result.chunk_id,
                )

        result.validation_errors = errors
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_refined_user_prompt(original_text: str, errors: list[str]) -> str:
        """Build a retry user prompt that includes prior validation errors."""
        error_block = "\n".join(f"- {e}" for e in errors)
        return (
            f"The previous extraction had the following validation errors:\n"
            f"{error_block}\n\n"
            f"Please re-extract the data from the text below, fixing all errors.\n\n"
            f"{original_text}"
        )
