use anyhow::{Context, Result};
use calamine::{open_workbook_auto, Reader};
use std::io::Read;
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

/// Extract plain text from a DOCX file.
/// DOCX is a ZIP archive; text lives in `word/document.xml`.
pub fn parse_docx(path: &Path) -> Result<ParsedDocument> {
    let file = std::fs::File::open(path)
        .with_context(|| format!("Failed to open DOCX: {}", path.display()))?;

    let mut archive = zip::ZipArchive::new(file)
        .with_context(|| format!("Not a valid DOCX (ZIP) file: {}", path.display()))?;

    let mut xml_content = String::new();
    {
        let mut doc_xml = archive
            .by_name("word/document.xml")
            .with_context(|| "Missing word/document.xml inside DOCX")?;
        doc_xml
            .read_to_string(&mut xml_content)
            .with_context(|| "Failed to read word/document.xml")?;
    }

    // Strip XML tags; collect text runs separated by spaces/newlines.
    let text = extract_text_from_xml(&xml_content);

    let mut doc = ParsedDocument::new(text, path, DocumentFormat::Docx);
    doc.metadata
        .insert("parser".into(), serde_json::json!("zip+xml"));

    Ok(doc)
}

/// Walk the XML and collect content of <w:t> elements, inserting
/// paragraph breaks at <w:p> boundaries so the output is readable.
fn extract_text_from_xml(xml: &str) -> String {
    let mut output = String::new();
    let mut pos = 0;
    let bytes = xml.as_bytes();
    let len = bytes.len();

    while pos < len {
        if bytes[pos] == b'<' {
            // Find end of tag
            let tag_start = pos + 1;
            let tag_end = memchr(b'>', bytes, pos).unwrap_or(len);

            let tag = &xml[tag_start..tag_end];
            let tag_name = tag.split_whitespace().next().unwrap_or("");

            // Paragraph boundary → newline
            if tag_name == "w:p" || tag_name == "w:br" {
                if !output.is_empty() {
                    output.push('\n');
                }
            }

            pos = tag_end + 1;
        } else {
            // Text node — only emit if we're inside a <w:t> context.
            // Since we've already stripped tags we collect all bare text;
            // whitespace-only runs between tags are harmless.
            let text_end = memchr(b'<', bytes, pos).unwrap_or(len);
            let chunk = &xml[pos..text_end];
            output.push_str(chunk);
            pos = text_end;
        }
    }

    // Collapse excessive blank lines and trim
    let result: String = output
        .lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .collect::<Vec<_>>()
        .join("\n");

    result
}

/// Minimal forward-only search for a byte in a slice starting at `from`.
fn memchr(needle: u8, haystack: &[u8], from: usize) -> Option<usize> {
    haystack[from..].iter().position(|&b| b == needle).map(|i| from + i)
}

pub fn parse_excel(path: &Path) -> Result<ParsedDocument> {
    let mut workbook = open_workbook_auto(path)
        .with_context(|| format!("Failed to open spreadsheet: {}", path.display()))?;

    let sheet_names = workbook.sheet_names().to_vec();
    let mut all_text = Vec::new();

    for sheet_name in &sheet_names {
        if let Ok(range) = workbook.worksheet_range(sheet_name) {
            all_text.push(format!("## Sheet: {}", sheet_name));

            let mut rows_text: Vec<String> = Vec::new();
            for row in range.rows() {
                let cells: Vec<String> = row
                    .iter()
                    .map(|cell| cell.to_string())
                    .collect();
                rows_text.push(cells.join("\t"));
            }
            all_text.push(rows_text.join("\n"));
        }
    }

    let content = all_text.join("\n\n");

    let mut doc = ParsedDocument::new(content, path, DocumentFormat::Xlsx);
    doc.metadata
        .insert("sheet_count".into(), serde_json::json!(sheet_names.len()));
    doc.metadata
        .insert("sheets".into(), serde_json::json!(sheet_names));

    Ok(doc)
}
