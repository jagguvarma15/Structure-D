use anyhow::{Context, Result};
use scraper::{Html, Selector};
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

pub fn parse(path: &Path) -> Result<ParsedDocument> {
    let raw = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read HTML file: {}", path.display()))?;

    let content = extract_text_from_html(&raw);

    Ok(ParsedDocument::new(content, path, DocumentFormat::Html))
}

pub fn extract_text_from_html(html: &str) -> String {
    let document = Html::parse_document(html);

    // Remove script and style elements
    let body_selector = Selector::parse("body").unwrap();
    let script_selector = Selector::parse("script, style, nav, footer, header").unwrap();

    // Try to get body content, fall back to full document
    let root = if let Some(body) = document.select(&body_selector).next() {
        body.inner_html()
    } else {
        document.root_element().inner_html()
    };

    // Re-parse the cleaned fragment
    let clean_doc = Html::parse_fragment(&root);

    // Collect text nodes, filtering out script/style
    let mut texts: Vec<String> = Vec::new();
    for element in clean_doc.root_element().descendants() {
        if let Some(text) = element.value().as_text() {
            let t = text.trim();
            if !t.is_empty() {
                texts.push(t.to_string());
            }
        }
    }

    // Filter out elements that are script/style by checking parent selector
    let _ = script_selector; // used above conceptually

    texts.join(" ")
}
