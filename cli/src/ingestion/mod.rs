pub mod detect;
pub mod email;
pub mod html;
pub mod office;
pub mod pdf;
pub mod text;

// Re-export the detection API so callers only need `crate::ingestion::*`.
#[allow(unused_imports)]
pub use detect::{detect_format, possible_outputs, OutputFormat};

use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use uuid::Uuid;

// ── Document format enum ──────────────────────────────────────────────────────

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
            DocumentFormat::Pdf       => "PDF",
            DocumentFormat::Docx      => "Word (DOCX)",
            DocumentFormat::Xlsx      => "Excel (XLSX)",
            DocumentFormat::Pptx      => "PowerPoint (PPTX)",
            DocumentFormat::Html      => "HTML",
            DocumentFormat::Email     => "Email (EML/MSG)",
            DocumentFormat::PlainText => "Plain Text",
            DocumentFormat::Markdown  => "Markdown",
            DocumentFormat::Csv       => "CSV",
            DocumentFormat::Image     => "Image",
            DocumentFormat::Audio     => "Audio/Transcript",
            DocumentFormat::Unknown   => "Unknown",
        };
        write!(f, "{s}")
    }
}

// ── ParsedDocument ────────────────────────────────────────────────────────────

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

// ── parse_file ────────────────────────────────────────────────────────────────

/// Parse a file into a [`ParsedDocument`].
///
/// Format is auto-detected via [`detect_format`] (magic bytes → extension regex →
/// content sniffing) unless `parser_override` is supplied.
pub fn parse_file(path: &Path, parser_override: Option<&str>) -> Result<ParsedDocument> {
    let format = match parser_override {
        Some(ov) => override_to_format(ov)?,
        None     => detect_format(path),
    };

    match &format {
        DocumentFormat::Pdf       => pdf::parse(path),
        DocumentFormat::Docx      => office::parse_docx(path),
        DocumentFormat::Xlsx      => office::parse_excel(path),
        DocumentFormat::Html      => html::parse(path),
        DocumentFormat::Email     => email::parse(path),
        // All text-family formats go through the same parser
        DocumentFormat::Markdown
        | DocumentFormat::Csv
        | DocumentFormat::PlainText => text::parse(path),
        // Audio transcripts (SRT/VTT) are plain text
        DocumentFormat::Audio     => text::parse(path),
        DocumentFormat::Image     => bail!(
            "Image parsing requires OCR (not yet in the Rust CLI). \
             Use the Python SDK with Tesseract/EasyOCR enabled."
        ),
        DocumentFormat::Pptx      => bail!(
            "PPTX parsing is not yet implemented in the Rust CLI. \
             Use the Python SDK with python-pptx enabled."
        ),
        DocumentFormat::Unknown   => bail!(
            "Cannot determine file format for '{}'. \
             Use --parser <format> to specify it explicitly.",
            path.display()
        ),
    }
}

/// Convert a `--parser` override string to a [`DocumentFormat`].
fn override_to_format(s: &str) -> Result<DocumentFormat> {
    match s.to_lowercase().as_str() {
        "pdf"                            => Ok(DocumentFormat::Pdf),
        "docx" | "doc"                   => Ok(DocumentFormat::Docx),
        "xlsx" | "xls" | "ods"          => Ok(DocumentFormat::Xlsx),
        "pptx" | "ppt"                   => Ok(DocumentFormat::Pptx),
        "html" | "htm"                   => Ok(DocumentFormat::Html),
        "eml" | "email" | "msg"         => Ok(DocumentFormat::Email),
        "md" | "markdown" | "rst"       => Ok(DocumentFormat::Markdown),
        "csv" | "tsv"                    => Ok(DocumentFormat::Csv),
        "txt" | "text" | "log"          => Ok(DocumentFormat::PlainText),
        "image" | "png" | "jpg" | "jpeg" => Ok(DocumentFormat::Image),
        "audio" | "srt" | "vtt"         => Ok(DocumentFormat::Audio),
        other => bail!(
            "Unknown parser override '{}'. \
             Valid: pdf, docx, xlsx, pptx, html, eml, md, csv, txt, image, audio",
            other
        ),
    }
}

// ── Human-readable format list (used by `formats` command) ───────────────────

pub const SUPPORTED_FORMATS: &[(&str, &str)] = &[
    ("pdf",              "PDF documents (lopdf)"),
    ("html / htm",       "Web pages (scraper)"),
    ("xlsx / xls / ods", "Spreadsheets (calamine)"),
    ("eml / msg",        "Email files (mailparse)"),
    ("txt / md / csv / srt", "Plain text, Markdown, CSV, transcripts"),
    ("docx",             "Word documents (ZIP/XML parser)"),
];
