"""Utility functions for common operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ── File operations ──────────────────────────────────────────────────────────────


def ensure_directory(path: Path | str) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_read_json(path: Path | str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safely read a JSON file, returning default if file doesn't exist or is invalid."""
    p = Path(path)
    if not p.exists():
        return default or {}
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("failed_to_read_json", path=str(p), error=str(e))
        return default or {}


def safe_write_json(data: dict[str, Any] | list[Any], path: Path | str, indent: int = 2) -> None:
    """Safely write data to a JSON file."""
    p = Path(path)
    ensure_directory(p.parent)
    with open(p, "w") as f:
        json.dump(data, f, indent=indent, default=str)


def get_file_size_mb(path: Path | str) -> float:
    """Get file size in megabytes."""
    return Path(path).stat().st_size / (1024 * 1024)


# ── JSON handling ────────────────────────────────────────────────────────────────


def extract_json_from_text(text: str) -> dict[str, Any] | list[Any] | None:
    """
    Extract JSON object or array from text that may contain extra content.
    
    Returns the first valid JSON found, or None if none found.
    """
    # Try to find JSON object
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        pass
    
    # Try to find JSON array
    start = text.find("[")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        pass
    
    return None


def format_error_message(
    error: Exception,
    *,
    context: dict[str, str] | None = None,
    include_traceback: bool = False,
) -> str:
    """Format an error message with context."""
    parts = [f"{type(error).__name__}: {str(error)}"]
    
    if context:
        ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
        parts.append(f"Context: {ctx_str}")
    
    if include_traceback and hasattr(error, "__traceback__"):
        import traceback
        parts.append(f"\nTraceback:\n{traceback.format_exc()}")
    
    return " | ".join(parts)


# ── String operations ───────────────────────────────────────────────────────────


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace: collapse multiple spaces, strip lines."""
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


# ── Type conversions ─────────────────────────────────────────────────────────────


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float, returning default on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ── URL/Path validation ─────────────────────────────────────────────────────────


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL."""
    from urllib.parse import urlparse
    
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def is_valid_path(path: str | Path) -> bool:
    """Check if a path exists and is accessible."""
    try:
        return Path(path).exists()
    except Exception:
        return False
