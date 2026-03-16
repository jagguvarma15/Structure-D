use anyhow::{Context, Result};
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

pub fn parse(path: &Path) -> Result<ParsedDocument> {
    // ── Text extraction ───────────────────────────────────────────────────────
    // `pdf-extract` handles ToUnicode CMap, CID/Type0 composite fonts, and
    // other encoding variants that `lopdf::extract_text` silently fails on.
    let content = pdf_extract::extract_text(path)
        .with_context(|| format!("Failed to extract text from PDF: {}", path.display()))?;

    // ── Page count (best-effort via lopdf) ────────────────────────────────────
    // lopdf is still reliable for structural metadata even when it cannot
    // decode the text layer.
    let page_count = lopdf::Document::load(path)
        .ok()
        .map(|d| d.get_pages().len());

    let mut doc_result = ParsedDocument::new(content, path, DocumentFormat::Pdf);
    doc_result.page_count = page_count;
    if let Some(n) = page_count {
        doc_result
            .metadata
            .insert("page_count".into(), serde_json::json!(n));
    }

    Ok(doc_result)
}
