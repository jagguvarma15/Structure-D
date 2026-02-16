"""Retry / fallback logic for validation failures."""

from __future__ import annotations

import re
from typing import Any, Type

import structlog
from pydantic import BaseModel

from structure_d.config import get_settings
from structure_d.inference.structured_output import StructuredOutputBuilder
from structure_d.inference.vllm_client import VLLMClient
from structure_d.schemas.base import ExtractionResult, TaskType
from structure_d.validation.validator import SchemaValidator

logger = structlog.get_logger(__name__)


class RetryHandler:
    """
    Wraps validation + retry logic:
    1. Validate the raw output.
    2. If invalid and retries remain, send a refined prompt to the LLM.
    3. If all retries fail and fallback_to_regex is on, try regex extraction.
    """

    def __init__(
        self,
        schema_cls: Type[BaseModel],
        task: TaskType = TaskType.EXTRACTION,
        client: VLLMClient | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.schema_cls = schema_cls
        self.task = task
        self.validator = SchemaValidator(schema_cls)
        self.client = client or VLLMClient()
        self.max_retries = max_retries or settings.validation.max_retries
        self.retry_with_prompt = settings.validation.retry_with_refined_prompt
        self.fallback_regex = settings.validation.fallback_to_regex
        self.builder = StructuredOutputBuilder(schema_cls=schema_cls, task=task)

    async def validate_and_retry(
        self,
        result: ExtractionResult,
        original_text: str,
        model: str,
    ) -> ExtractionResult:
        """
        Validate *result.raw_output* and retry if needed.

        Mutates and returns the same :class:`ExtractionResult`.
        """
        structured, errors = self.validator.validate(result.raw_output)

        if not errors:
            result.structured_output = structured
            result.is_valid = True
            return result

        # Retry loop
        current_raw = result.raw_output
        for attempt in range(1, self.max_retries + 1):
            if not self.retry_with_prompt:
                break

            logger.info(
                "validation_retry",
                attempt=attempt,
                errors=errors,
                chunk_id=result.chunk_id,
            )

            messages = self.builder.build_refined_prompt(original_text, errors)
            schema = self.builder.json_schema()

            response = await self.client.chat(
                model=model,
                messages=messages,
                json_schema=schema,
            )

            choices = response.get("choices", [])
            if choices:
                current_raw = choices[0].get("message", {}).get("content", "")

            structured, errors = self.validator.validate(current_raw)
            if not errors:
                result.raw_output = current_raw
                result.structured_output = structured
                result.is_valid = True
                return result

        # Fallback: regex extraction
        if self.fallback_regex and errors:
            logger.info("validation_fallback_regex", chunk_id=result.chunk_id)
            structured = self._regex_fallback(result.raw_output)
            if structured:
                re_structured, re_errors = self.validator.validate_dict(structured)
                if not re_errors:
                    result.structured_output = re_structured
                    result.is_valid = True
                    result.validation_errors = []
                    return result

        result.structured_output = structured
        result.is_valid = False
        result.validation_errors = errors
        return result

    # ── Regex fallback ────────────────────────────────────────────────────────

    @staticmethod
    def _regex_fallback(raw: str) -> dict[str, Any]:
        """
        Best-effort extraction of key-value pairs using simple regex.
        Looks for patterns like ``"key": "value"`` or ``"key": 123``.
        """
        pairs: dict[str, Any] = {}
        for m in re.finditer(r'"(\w+)"\s*:\s*"([^"]*)"', raw):
            pairs[m.group(1)] = m.group(2)
        for m in re.finditer(r'"(\w+)"\s*:\s*(\d+(?:\.\d+)?)', raw):
            val = m.group(2)
            pairs[m.group(1)] = float(val) if "." in val else int(val)
        return pairs
