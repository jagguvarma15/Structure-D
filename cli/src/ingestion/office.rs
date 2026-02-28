use anyhow::{Context, Result};
use calamine::{open_workbook_auto, Reader};
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

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
