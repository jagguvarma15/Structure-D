use anyhow::{Context, Result};
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

pub fn parse(path: &Path) -> Result<ParsedDocument> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read file: {}", path.display()))?;

    let format = match path.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase().as_str() {
        "md" | "markdown" => DocumentFormat::Markdown,
        "csv" => DocumentFormat::Csv,
        _ => DocumentFormat::PlainText,
    };

    Ok(ParsedDocument::new(content, path, format))
}

/// Fallback: try to read any file as UTF-8 text.
pub fn parse_as_text(path: &Path) -> Result<ParsedDocument> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read file as text: {}", path.display()))?;
    Ok(ParsedDocument::new(content, path, DocumentFormat::PlainText))
}
