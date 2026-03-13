"""Tests for StructuredOutputBuilder: prompt generation and JSON schema output."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from structure_d.inference.structured_output import StructuredOutputBuilder
from structure_d.schemas.base import TaskType
from structure_d.schemas.generic import KeyValueExtraction


class _SimpleSchema(BaseModel):
    name: str
    age: int = Field(description="Person's age")


def test_json_schema_matches_pydantic():
    """json_schema() should return the same dict as model_json_schema()."""
    builder = StructuredOutputBuilder(_SimpleSchema)
    assert builder.json_schema() == _SimpleSchema.model_json_schema()


def test_build_system_prompt_contains_schema():
    """System prompt should embed the JSON schema text."""
    builder = StructuredOutputBuilder(KeyValueExtraction)
    prompt = builder.build_system_prompt()
    assert "pairs" in prompt
    assert "key" in prompt
    assert "value" in prompt
    assert "JSON" in prompt


def test_build_system_prompt_custom_override():
    """A custom system prompt should replace the auto-generated one entirely."""
    builder = StructuredOutputBuilder(
        _SimpleSchema, custom_system_prompt="You are a test bot."
    )
    assert builder.build_system_prompt() == "You are a test bot."


def test_build_system_prompt_few_shot():
    """Few-shot examples should appear in the system prompt."""
    examples = [{"input": "doc text", "output": '{"name": "Bob", "age": 42}'}]
    builder = StructuredOutputBuilder(_SimpleSchema, few_shot_examples=examples)
    prompt = builder.build_system_prompt()
    assert "doc text" in prompt
    assert "Bob" in prompt


def test_build_messages_structure():
    """build_messages should return [system, user] message dicts."""
    builder = StructuredOutputBuilder(_SimpleSchema)
    msgs = builder.build_messages("Extract from this text")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Extract from this text"


def test_build_messages_no_system():
    """include_system=False should omit the system message."""
    builder = StructuredOutputBuilder(_SimpleSchema)
    msgs = builder.build_messages("text", include_system=False)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"


def test_build_refined_prompt_includes_errors():
    """Refined retry prompt should include both the errors and original text."""
    builder = StructuredOutputBuilder(_SimpleSchema)
    msgs = builder.build_refined_prompt("original text", ["missing 'name'"])
    user_msg = msgs[-1]["content"]
    assert "missing 'name'" in user_msg
    assert "original text" in user_msg
    assert "validation errors" in user_msg.lower()
