"""Tests verifying custom exception types carry their extra attributes."""

from __future__ import annotations

from structure_d.exceptions import (
    ConfigurationError,
    InferenceError,
    ModelRoutingError,
    ParserError,
    RetrievalError,
    StorageError,
    StructureDError,
    ValidationError,
)


def test_base_error_stores_context():
    """StructureDError should store message and context dict."""
    err = StructureDError("boom", context={"key": "val"})
    assert str(err) == "boom"
    assert err.message == "boom"
    assert err.context == {"key": "val"}


def test_parser_error_attributes():
    """ParserError should carry file_path, parser_name, and format."""
    err = ParserError(
        "bad file",
        file_path="/tmp/x.pdf",
        parser_name="pymupdf",
        format=".pdf",
    )
    assert err.file_path == "/tmp/x.pdf"
    assert err.parser_name == "pymupdf"
    assert err.format == ".pdf"


def test_validation_error_attributes():
    """ValidationError should carry schema_name, errors list, and raw_output."""
    err = ValidationError(
        "invalid",
        schema_name="KeyValue",
        validation_errors=["missing field"],
        raw_output="{}",
    )
    assert err.schema_name == "KeyValue"
    assert err.validation_errors == ["missing field"]
    assert err.raw_output == "{}"


def test_inference_error_attributes():
    """InferenceError should carry model, status_code, response_body."""
    err = InferenceError(
        "timeout", model="gpt-4", status_code=504, response_body="gateway timeout",
    )
    assert err.model == "gpt-4"
    assert err.status_code == 504
    assert err.response_body == "gateway timeout"


def test_configuration_error_attributes():
    """ConfigurationError should carry config_key and config_path."""
    err = ConfigurationError("bad key", config_key="foo.bar", config_path="/etc/conf.yaml")
    assert err.config_key == "foo.bar"
    assert err.config_path == "/etc/conf.yaml"


def test_model_routing_error_attributes():
    """ModelRoutingError should carry task and available_models."""
    err = ModelRoutingError("no model", task="extraction", available_models=["a", "b"])
    assert err.task == "extraction"
    assert err.available_models == ["a", "b"]


def test_storage_error_attributes():
    """StorageError should carry storage_type and file_path."""
    err = StorageError("write failed", storage_type="jsonl", file_path="/out/data.jsonl")
    assert err.storage_type == "jsonl"
    assert err.file_path == "/out/data.jsonl"


def test_retrieval_error_attributes():
    """RetrievalError should carry vector_store and operation."""
    err = RetrievalError("query failed", vector_store="chroma", operation="query")
    assert err.vector_store == "chroma"
    assert err.operation == "query"


def test_all_exceptions_inherit_from_base():
    """Every custom exception should be a subclass of StructureDError."""
    for cls in (
        ParserError,
        ValidationError,
        InferenceError,
        ConfigurationError,
        ModelRoutingError,
        StorageError,
        RetrievalError,
    ):
        assert issubclass(cls, StructureDError)
