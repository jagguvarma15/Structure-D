"""Pydantic / JSON Schema validation for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any, Type

import structlog
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger(__name__)


class SchemaValidator:
    """
    Validate raw LLM output against a Pydantic model.

    Steps:
    1. Attempt to parse the raw string as JSON.
    2. If that fails, try to extract a JSON object/array from the string.
    3. Validate the parsed data against the Pydantic model.
    """

    def __init__(self, schema_cls: Type[BaseModel]) -> None:
        self.schema_cls = schema_cls

    def validate(self, raw: str) -> tuple[dict[str, Any] | list[Any], list[str]]:
        """
        Parse and validate *raw*.

        Returns
        -------
        (structured_data, errors)
            If validation succeeds, *errors* is empty and *structured_data*
            contains the model-dumped dict.  Otherwise *structured_data* is
            the best-effort parsed data and *errors* lists the issues.
        """
        parsed, parse_errors = self._parse_json(raw)
        if parse_errors:
            return parsed, parse_errors

        return self._validate_against_schema(parsed)

    def validate_dict(self, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Validate an already-parsed dict."""
        return self._validate_against_schema(data)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _parse_json(self, raw: str) -> tuple[Any, list[str]]:
        """Try to extract valid JSON from *raw*."""
        raw = raw.strip()

        # 1. Direct parse
        try:
            return json.loads(raw), []
        except json.JSONDecodeError:
            pass

        # 2. Try to find a JSON block in markdown code fences
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip()), []
            except json.JSONDecodeError:
                pass

        # 3. Try to find the first { ... } or [ ... ] in the string
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = raw.find(start_char)
            end = raw.rfind(end_char)
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1]), []
                except json.JSONDecodeError:
                    pass

        return {}, [f"Could not parse JSON from output: {raw[:200]}..."]

    def _validate_against_schema(
        self, data: Any
    ) -> tuple[dict[str, Any] | list[Any], list[str]]:
        errors: list[str] = []

        # Handle list of objects
        if isinstance(data, list):
            validated: list[Any] = []
            for i, item in enumerate(data):
                try:
                    obj = self.schema_cls.model_validate(item)
                    validated.append(obj.model_dump())
                except ValidationError as e:
                    for err in e.errors():
                        errors.append(f"Item {i}: {err['loc']} – {err['msg']}")
                    validated.append(item)
            return validated, errors

        # Single object
        try:
            obj = self.schema_cls.model_validate(data)
            return obj.model_dump(), []
        except ValidationError as e:
            for err in e.errors():
                loc = " → ".join(str(l) for l in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
            return data if isinstance(data, dict) else {}, errors
