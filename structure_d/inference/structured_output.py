"""Helpers for building structured output prompts and schemas."""

from __future__ import annotations

import json
from typing import Any, Type

from pydantic import BaseModel

from structure_d.schemas.base import TaskType

# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are a precise data extraction assistant. Your task is to extract structured
information from the provided text and return it as valid JSON that conforms
exactly to the given schema.

## Output schema
{schema}

## Rules
- Return ONLY the JSON object, no surrounding text.
- If a field cannot be found, use null.
- Do not hallucinate; only extract what is explicitly present.
"""

_FEW_SHOT_TEMPLATE = """\

## Example
Input: {example_input}
Output: {example_output}
"""


class StructuredOutputBuilder:
    """
    Build system/user messages and JSON schemas for structured extraction.

    Usage::

        builder = StructuredOutputBuilder(InvoiceSchema)
        messages = builder.build_messages(text_chunk)
        schema = builder.json_schema()
    """

    def __init__(
        self,
        schema_cls: Type[BaseModel],
        task: TaskType = TaskType.EXTRACTION,
        few_shot_examples: list[dict[str, str]] | None = None,
        custom_system_prompt: str | None = None,
    ) -> None:
        self.schema_cls = schema_cls
        self.task = task
        self.few_shot_examples = few_shot_examples or []
        self.custom_system_prompt = custom_system_prompt

    def json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema derived from the Pydantic model."""
        return self.schema_cls.model_json_schema()

    def build_system_prompt(self) -> str:
        """Build the system prompt including the schema and optional few-shot examples."""
        if self.custom_system_prompt:
            return self.custom_system_prompt

        schema_str = json.dumps(self.json_schema(), indent=2)
        prompt = _SYSTEM_TEMPLATE.format(schema=schema_str)

        for ex in self.few_shot_examples:
            prompt += _FEW_SHOT_TEMPLATE.format(
                example_input=ex.get("input", ""),
                example_output=ex.get("output", ""),
            )

        return prompt

    def build_messages(
        self,
        user_text: str,
        *,
        include_system: bool = True,
    ) -> list[dict[str, str]]:
        """Return a list of chat messages ready for the vLLM client."""
        msgs: list[dict[str, str]] = []
        if include_system:
            msgs.append({"role": "system", "content": self.build_system_prompt()})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def build_refined_prompt(self, user_text: str, errors: list[str]) -> list[dict[str, str]]:
        """
        Build a retry prompt that includes the original text plus validation errors
        so the model can self-correct.
        """
        error_block = "\n".join(f"- {e}" for e in errors)
        retry_msg = (
            f"The previous extraction had the following validation errors:\n"
            f"{error_block}\n\n"
            f"Please re-extract the data from the text below, fixing the errors.\n\n"
            f"{user_text}"
        )
        return self.build_messages(retry_msg)
