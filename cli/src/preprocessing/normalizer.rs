use regex::Regex;
use std::sync::OnceLock;
use unicode_normalization::UnicodeNormalization;

static RE_PAGE_NUMBER: OnceLock<Regex> = OnceLock::new();
static RE_MULTIPLE_NEWLINES: OnceLock<Regex> = OnceLock::new();
static RE_MULTIPLE_SPACES: OnceLock<Regex> = OnceLock::new();
static RE_CONTROL_CHARS: OnceLock<Regex> = OnceLock::new();

fn re_page_number() -> &'static Regex {
    RE_PAGE_NUMBER.get_or_init(|| {
        Regex::new(r"(?m)^\s*-?\s*\d+\s*-?\s*$").unwrap()
    })
}

fn re_multiple_newlines() -> &'static Regex {
    RE_MULTIPLE_NEWLINES.get_or_init(|| Regex::new(r"\n{3,}").unwrap())
}

fn re_multiple_spaces() -> &'static Regex {
    RE_MULTIPLE_SPACES.get_or_init(|| Regex::new(r"[ \t]{2,}").unwrap())
}

fn re_control_chars() -> &'static Regex {
    RE_CONTROL_CHARS.get_or_init(|| Regex::new(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]").unwrap())
}

/// Normalize text: Unicode NFC, strip control chars, collapse whitespace, remove boilerplate.
pub fn normalize_text(text: &str, normalize_unicode: bool, strip_boilerplate: bool, collapse_whitespace: bool) -> String {
    let mut s = text.to_string();

    if normalize_unicode {
        // NFC normalization + remove non-printable control characters
        s = s.nfc().collect::<String>();
        s = re_control_chars().replace_all(&s, "").to_string();
    }

    if strip_boilerplate {
        // Remove lone page numbers (e.g., lines that are just "- 3 -" or "42")
        s = re_page_number().replace_all(&s, "").to_string();
    }

    if collapse_whitespace {
        // Collapse multiple spaces/tabs to single space
        s = re_multiple_spaces().replace_all(&s, " ").to_string();
        // Collapse 3+ newlines to double newline
        s = re_multiple_newlines().replace_all(&s, "\n\n").to_string();
        s = s.trim().to_string();
    }

    s
}
