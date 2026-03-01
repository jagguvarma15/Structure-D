pub mod email;
pub mod html;
pub mod office;
pub mod pdf;
pub mod text;

use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DocumentFormat {
    Pdf,
    Docx,
    Xlsx,
    Pptx,
    Html,
    Email,
    PlainText,
    Markdown,
    Csv,
    Image,
    Audio,
    Unknown,
}

impl std::fmt::Display for DocumentFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            DocumentFormat::Pdf => "pdf",
            DocumentFormat::Docx => "docx",
            DocumentFormat::Xlsx => "xlsx",
            DocumentFormat::Pptx => "pptx",
            DocumentFormat::Html => "html",
            DocumentFormat::Email => "email",
            DocumentFormat::PlainText => "text",
            DocumentFormat::Markdown => "markdown",
            DocumentFormat::Csv => "csv",
            DocumentFormat::Image => "image",
            DocumentFormat::Audio => "audio",
            DocumentFormat::Unknown => "unknown",
        };
        write!(f, "{s}")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedDocument {
    pub id: Uuid,
    pub content: String,
    pub source_path: String,
    pub format: DocumentFormat,
    pub page_count: Option<usize>,
    pub metadata: HashMap<String, serde_json::Value>,
}

impl ParsedDocument {
    pub fn new(content: String, source_path: &Path, format: DocumentFormat) -> Self {
        Self {
            id: Uuid::new_v4(),
            content,
            source_path: source_path.display().to_string(),
            format,
            page_count: None,
            metadata: HashMap::new(),
        }
    }
}

/// Auto-dispatch to the right parser based on file extension.
pub fn parse_file(path: &Path, parser_override: Option<&str>) -> Result<ParsedDocument> {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let effective_parser = parser_override.unwrap_or(&ext);

    match effective_parser {
        "pdf" => pdf::parse(path),
        "html" | "htm" => html::parse(path),
        "xlsx" | "xls" | "ods" => office::parse_excel(path),
        "eml" | "email" | "msg" => email::parse(path),
        "txt" | "md" | "markdown" | "csv" | "tsv" | "log" | "rst" => text::parse(path),
        "docx" => office::parse_docx(path),
        other => bail!(
            "Unsupported file format '{}'. Supported: pdf, html, xlsx, eml, txt, md, csv",
            other
        ),
    }
}

pub const SUPPORTED_FORMATS: &[(&str, &str)] = &[
    ("pdf", "PDF documents (lopdf)"),
    ("html / htm", "Web pages (scraper)"),
    ("xlsx / xls", "Spreadsheets (calamine)"),
    ("eml", "Email files (mailparse)"),
    ("txt / md / csv / log", "Plain text, Markdown, CSV, log files"),
    ("docx", "Word documents (ZIP/XML parser)"),
];
