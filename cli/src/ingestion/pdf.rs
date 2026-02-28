use anyhow::{Context, Result};
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

pub fn parse(path: &Path) -> Result<ParsedDocument> {
    let doc = lopdf::Document::load(path)
        .with_context(|| format!("Failed to load PDF: {}", path.display()))?;

    let page_count = doc.get_pages().len();
    let mut pages_text: Vec<String> = Vec::with_capacity(page_count);

    for (page_num, _page_id) in doc.get_pages() {
        match doc.extract_text(&[page_num]) {
            Ok(text) => pages_text.push(text),
            Err(_) => pages_text.push(String::new()),
        }
    }

    let content = pages_text.join("\n\n");

    let mut doc_result = ParsedDocument::new(content, path, DocumentFormat::Pdf);
    doc_result.page_count = Some(page_count);
    doc_result
        .metadata
        .insert("page_count".into(), serde_json::json!(page_count));

    Ok(doc_result)
}
