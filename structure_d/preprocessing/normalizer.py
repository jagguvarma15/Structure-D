"""Text normalisation utilities."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(
    text: str,
    *,
    normalize_unicode: bool = True,
    strip_boilerplate: bool = True,
    collapse_whitespace: bool = True,
) -> str:
    """
    Clean and normalise raw text.

    Parameters
    ----------
    text:
        Raw input text.
    normalize_unicode:
        Convert to NFC form and strip control characters.
    strip_boilerplate:
        Remove common boilerplate patterns (page numbers, headers/footers).
    collapse_whitespace:
        Replace runs of whitespace with a single space/newline.
    """
    if normalize_unicode:
        text = unicodedata.normalize("NFC", text)
        # Remove control characters except newlines and tabs
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    if strip_boilerplate:
        # Remove standalone page-number lines  (e.g. "Page 3", "– 12 –", "3")
        text = re.sub(r"(?m)^\s*[-–—]*\s*(?:page\s*)?\d+\s*[-–—]*\s*$", "", text, flags=re.IGNORECASE)

    if collapse_whitespace:
        # Collapse multiple blank lines into one
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse multiple spaces (preserve newlines)
        text = re.sub(r"[^\S\n]+", " ", text)

    return text.strip()
