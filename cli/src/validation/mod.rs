pub mod retry;

use anyhow::Result;
use regex::Regex;
use serde_json::Value;
use std::sync::OnceLock;

static RE_JSON_FENCE: OnceLock<Regex> = OnceLock::new();
static RE_JSON_OBJECT: OnceLock<Regex> = OnceLock::new();
static RE_JSON_ARRAY: OnceLock<Regex> = OnceLock::new();

fn re_json_fence() -> &'static Regex {
    RE_JSON_FENCE.get_or_init(|| {
        Regex::new(r"(?s)```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```").unwrap()
    })
}

fn re_json_object() -> &'static Regex {
    RE_JSON_OBJECT.get_or_init(|| Regex::new(r"(?s)\{.*\}").unwrap())
}

fn re_json_array() -> &'static Regex {
    RE_JSON_ARRAY.get_or_init(|| Regex::new(r"(?s)\[.*\]").unwrap())
}

#[derive(Debug, Clone)]
pub struct ValidationResult {
    pub data: Option<Value>,
    pub is_valid: bool,
    pub errors: Vec<String>,
    pub raw_output: String,
}

/// Attempt to extract and parse JSON from an LLM output string.
/// Strategies (in order):
///   1. Direct parse as JSON
///   2. Extract from ```json ... ``` fence
///   3. Find first { ... } block
///   4. Find first [ ... ] block
pub fn extract_json(text: &str) -> Result<Value, Vec<String>> {
    let trimmed = text.trim();

    // Strategy 1: direct parse
    if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
        return Ok(v);
    }

    // Strategy 2: markdown fence
    if let Some(cap) = re_json_fence().captures(trimmed) {
        if let Some(json_str) = cap.get(1) {
            if let Ok(v) = serde_json::from_str::<Value>(json_str.as_str()) {
                return Ok(v);
            }
        }
    }

    // Strategy 3: first { ... } block
    if let Some(m) = re_json_object().find(trimmed) {
        if let Ok(v) = serde_json::from_str::<Value>(m.as_str()) {
            return Ok(v);
        }
    }

    // Strategy 4: first [ ... ] block
    if let Some(m) = re_json_array().find(trimmed) {
        if let Ok(v) = serde_json::from_str::<Value>(m.as_str()) {
            return Ok(v);
        }
    }

    Err(vec![format!(
        "Could not extract valid JSON from LLM output. Raw (first 200 chars): {}",
        &trimmed[..trimmed.len().min(200)]
    )])
}

pub fn validate(raw_output: &str) -> ValidationResult {
    match extract_json(raw_output) {
        Ok(data) => ValidationResult {
            data: Some(data),
            is_valid: true,
            errors: vec![],
            raw_output: raw_output.to_string(),
        },
        Err(errors) => ValidationResult {
            data: None,
            is_valid: false,
            errors,
            raw_output: raw_output.to_string(),
        },
    }
}
