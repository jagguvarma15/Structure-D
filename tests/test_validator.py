"""Tests for the validation module."""

import json

from pydantic import BaseModel, Field

from structure_d.validation.validator import SchemaValidator


class SampleSchema(BaseModel):
    name: str
    age: int
    email: str | None = None


def test_valid_json():
    raw = json.dumps({"name": "Alice", "age": 30, "email": "alice@example.com"})
    validator = SchemaValidator(SampleSchema)
    data, errors = validator.validate(raw)
    assert not errors
    assert data["name"] == "Alice"
    assert data["age"] == 30


def test_json_in_markdown_block():
    raw = '```json\n{"name": "Bob", "age": 25}\n```'
    validator = SchemaValidator(SampleSchema)
    data, errors = validator.validate(raw)
    assert not errors
    assert data["name"] == "Bob"


def test_json_embedded_in_text():
    raw = 'Here is the result: {"name": "Carol", "age": 28} and some trailing text.'
    validator = SchemaValidator(SampleSchema)
    data, errors = validator.validate(raw)
    assert not errors
    assert data["name"] == "Carol"


def test_validation_error():
    raw = json.dumps({"name": "Dave", "age": "not-a-number"})
    validator = SchemaValidator(SampleSchema)
    data, errors = validator.validate(raw)
    assert len(errors) > 0


def test_invalid_json():
    raw = "This is not JSON at all."
    validator = SchemaValidator(SampleSchema)
    data, errors = validator.validate(raw)
    assert len(errors) > 0


def test_list_validation():
    raw = json.dumps([
        {"name": "Eve", "age": 22},
        {"name": "Frank", "age": "bad"},
    ])
    validator = SchemaValidator(SampleSchema)
    data, errors = validator.validate(raw)
    assert isinstance(data, list)
    assert len(data) == 2
    # First item valid, second has error
    assert len(errors) > 0
