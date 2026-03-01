//! Format detection: magic bytes → extension regex → content sniffing.
//!
//! Three-pass detection (most-to-least reliable):
//!   1. Magic bytes   — binary signatures (%PDF, PK ZIP-family, PNG/JPEG/GIF/WEBP)
//!   2. Extension regex — named-extension matching compiled once via `regex` crate
//!   3. Content sniff  — reads first 4 KB to detect HTML, email, CSV, Markdown

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::io::Read;
use std::path::Path;
use std::sync::OnceLock;

use super::DocumentFormat;

// ── Extension regex helpers (compiled once per pattern) ──────────────────────
//
// The macro generates a `fn <name>() -> &'static Regex` that initialises the
// regex exactly once and returns a reference to the compiled instance.
macro_rules! ext_regex {
    ($fn_name:ident, $pattern:literal) => {
        fn $fn_name() -> &'static Regex {
            static RE: OnceLock<Regex> = OnceLock::new();
            RE.get_or_init(|| Regex::new($pattern).unwrap())
        }
    };
}

ext_regex!(re_pdf,      r"(?i)\.pdf$");
ext_regex!(re_docx,     r"(?i)\.docx?$");
ext_regex!(re_xlsx,     r"(?i)\.(xlsx?|ods)$");
ext_regex!(re_pptx,     r"(?i)\.pptx?$");
ext_regex!(re_html,     r"(?i)\.html?$");
ext_regex!(re_email,    r"(?i)\.(eml|email|msg)$");
ext_regex!(re_image,    r"(?i)\.(png|jpe?g|gif|webp|bmp|tiff?)$");
ext_regex!(re_audio,    r"(?i)\.(srt|vtt|mp3|wav|m4a|ogg|flac)$");
ext_regex!(re_markdown, r"(?i)\.(md|markdown|rst)$");
ext_regex!(re_csv,      r"(?i)\.(csv|tsv)$");
ext_regex!(re_text,     r"(?i)\.(txt|log|text)$");

// ── Binary magic byte signatures ─────────────────────────────────────────────
const MAGIC_PDF:  &[u8] = b"%PDF";
const MAGIC_ZIP:  &[u8] = b"PK\x03\x04"; // ZIP-based: DOCX / XLSX / PPTX
const MAGIC_PNG:  &[u8] = b"\x89PNG\r\n\x1a\n";
const MAGIC_JPEG: &[u8] = &[0xFF, 0xD8, 0xFF];
const MAGIC_GIF:  &[u8] = b"GIF8";

fn has_magic(header: &[u8], magic: &[u8]) -> bool {
    header.len() >= magic.len() && &header[..magic.len()] == magic
}

fn read_header(path: &Path) -> Vec<u8> {
    let mut buf = vec![0u8; 16];
    if let Ok(mut f) = std::fs::File::open(path) {
        let n = f.read(&mut buf).unwrap_or(0);
        buf.truncate(n);
    }
    buf
}

// ── Content sniffing for text files ──────────────────────────────────────────

fn sniff_text(path: &Path) -> DocumentFormat {
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return DocumentFormat::PlainText,
    };
    let sample = &content[..content.len().min(4096)];

    // HTML: DOCTYPE declaration or structural tags
    static RE_HTML: OnceLock<Regex> = OnceLock::new();
    let re_html = RE_HTML.get_or_init(|| {
        Regex::new(r"(?i)(<!DOCTYPE\s+html|<html[\s>]|<body[\s>]|<head[\s>])").unwrap()
    });
    if re_html.is_match(sample) {
        return DocumentFormat::Html;
    }

    // Email: RFC 2822 header block (From / To / Subject / Date / MIME-Version)
    static RE_EMAIL: OnceLock<Regex> = OnceLock::new();
    let re_email = RE_EMAIL.get_or_init(|| {
        Regex::new(r"(?m)^(From|To|Subject|Date|MIME-Version):\s+\S").unwrap()
    });
    if re_email.is_match(sample) {
        return DocumentFormat::Email;
    }

    // CSV: more than 60% of non-empty lines contain at least one comma
    static RE_CSV_LINE: OnceLock<Regex> = OnceLock::new();
    let re_csv = RE_CSV_LINE.get_or_init(|| Regex::new(r"(?m)^[^\n]+,[^\n]+$").unwrap());
    let total_lines = sample.lines().filter(|l| !l.trim().is_empty()).count().max(1);
    let comma_lines = re_csv.find_iter(sample).count();
    if comma_lines * 10 > total_lines * 6 {
        return DocumentFormat::Csv;
    }

    // Markdown: ATX headings, bold, fenced code blocks, or inline links
    static RE_MD: OnceLock<Regex> = OnceLock::new();
    let re_md = RE_MD.get_or_init(|| {
        Regex::new(r"(?m)(^#{1,6}\s|```|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))").unwrap()
    });
    if re_md.is_match(sample) {
        return DocumentFormat::Markdown;
    }

    DocumentFormat::PlainText
}

// ── Public: detect_format ─────────────────────────────────────────────────────

/// Detect the document format of `path` using a three-pass strategy.
///
/// 1. **Magic bytes** — reads the first 16 bytes; reliable for binary formats.
/// 2. **Extension regex** — matches the full file path against known patterns.
/// 3. **Content sniffing** — reads the first 4 KB to disambiguate text formats.
pub fn detect_format(path: &Path) -> DocumentFormat {
    let path_str = path.to_string_lossy();
    let header = read_header(path);

    // ── Pass 1: binary magic bytes ────────────────────────────────────────────
    if has_magic(&header, MAGIC_PDF) {
        return DocumentFormat::Pdf;
    }
    if has_magic(&header, MAGIC_ZIP) {
        // ZIP-based Office formats — use extension to pick the right one
        if re_xlsx().is_match(&path_str) {
            return DocumentFormat::Xlsx;
        }
        if re_pptx().is_match(&path_str) {
            return DocumentFormat::Pptx;
        }
        if re_docx().is_match(&path_str) {
            return DocumentFormat::Docx;
        }
        return DocumentFormat::Unknown;
    }
    if has_magic(&header, MAGIC_PNG)
        || has_magic(&header, MAGIC_JPEG)
        || has_magic(&header, MAGIC_GIF)
    {
        return DocumentFormat::Image;
    }
    // WEBP: "RIFF????WEBP"
    if header.len() >= 12 && &header[..4] == b"RIFF" && &header[8..12] == b"WEBP" {
        return DocumentFormat::Image;
    }

    // ── Pass 2: extension regex ───────────────────────────────────────────────
    if re_pdf().is_match(&path_str)      { return DocumentFormat::Pdf; }
    if re_docx().is_match(&path_str)     { return DocumentFormat::Docx; }
    if re_xlsx().is_match(&path_str)     { return DocumentFormat::Xlsx; }
    if re_pptx().is_match(&path_str)     { return DocumentFormat::Pptx; }
    if re_html().is_match(&path_str)     { return DocumentFormat::Html; }
    if re_email().is_match(&path_str)    { return DocumentFormat::Email; }
    if re_image().is_match(&path_str)    { return DocumentFormat::Image; }
    if re_audio().is_match(&path_str)    { return DocumentFormat::Audio; }
    if re_csv().is_match(&path_str)      { return DocumentFormat::Csv; }
    if re_markdown().is_match(&path_str) { return DocumentFormat::Markdown; }
    if re_text().is_match(&path_str)     { return DocumentFormat::PlainText; }

    // ── Pass 3: content sniffing (text files with no recognised extension) ────
    sniff_text(path)
}

// ── Output format ─────────────────────────────────────────────────────────────

/// The target structured format a document can be converted into.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OutputFormat {
    Json,
    Jsonl,
    Csv,
    Markdown,
    PlainText,
}

impl std::fmt::Display for OutputFormat {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            OutputFormat::Json      => write!(f, "json"),
            OutputFormat::Jsonl     => write!(f, "jsonl"),
            OutputFormat::Csv       => write!(f, "csv"),
            OutputFormat::Markdown  => write!(f, "markdown"),
            OutputFormat::PlainText => write!(f, "txt"),
        }
    }
}

// ── Compatibility matrix ──────────────────────────────────────────────────────

/// Returns the output formats that make sense for the given input document type.
///
/// This is informational — use it to guide the user or warn about conversions
/// that won't produce useful results (e.g., Image → CSV without a schema).
pub fn possible_outputs(input: &DocumentFormat) -> Vec<OutputFormat> {
    use DocumentFormat as DF;
    use OutputFormat as OF;
    match input {
        DF::Pdf       => vec![OF::Json, OF::Jsonl, OF::Csv, OF::Markdown, OF::PlainText],
        DF::Docx      => vec![OF::Json, OF::Jsonl, OF::Csv, OF::Markdown, OF::PlainText],
        DF::Xlsx      => vec![OF::Json, OF::Jsonl, OF::Csv, OF::Markdown],     // tabular → CSV natural
        DF::Pptx      => vec![OF::Json, OF::Jsonl, OF::Markdown, OF::PlainText], // slides → outline
        DF::Html      => vec![OF::Json, OF::Jsonl, OF::Csv, OF::Markdown, OF::PlainText],
        DF::Email     => vec![OF::Json, OF::Jsonl, OF::Csv],                   // structured fields
        DF::Image     => vec![OF::Json, OF::Jsonl, OF::PlainText],             // OCR output
        DF::Audio     => vec![OF::Json, OF::Jsonl, OF::Markdown, OF::PlainText], // transcripts
        DF::Markdown  => vec![OF::Json, OF::Jsonl, OF::Csv, OF::PlainText],
        DF::Csv       => vec![OF::Json, OF::Jsonl, OF::Markdown],              // already structured
        DF::PlainText => vec![OF::Json, OF::Jsonl, OF::Csv, OF::Markdown],
        DF::Unknown   => vec![OF::Json, OF::Jsonl],                            // best-effort only
    }
}
