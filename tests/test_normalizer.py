"""Tests for text normalisation."""

from structure_d.preprocessing.normalizer import normalize_text


def test_collapse_whitespace():
    text = "Hello    world\n\n\n\nNew paragraph"
    result = normalize_text(text)
    assert "    " not in result
    assert "\n\n\n" not in result


def test_strip_page_numbers():
    text = "Some content.\n\nPage 3\n\nMore content."
    result = normalize_text(text, strip_boilerplate=True)
    assert "Page 3" not in result


def test_unicode_normalisation():
    # Combining character (e + combining acute) should become é
    text = "caf\u0065\u0301"
    result = normalize_text(text, normalize_unicode=True)
    assert "café" == result or "cafe\u0301" not in result


def test_noop():
    text = "Already clean text."
    result = normalize_text(
        text,
        normalize_unicode=False,
        strip_boilerplate=False,
        collapse_whitespace=False,
    )
    assert result == text
