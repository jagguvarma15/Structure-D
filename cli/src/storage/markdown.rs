use anyhow::{Context, Result};
use serde_json::Value;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use super::ExtractionResult;

pub struct MarkdownWriter {
    pub output_path: String,
}

impl MarkdownWriter {
    pub fn new(output_path: &str) -> Self {
        Self {
            output_path: output_path.to_string(),
        }
    }

    pub fn write(&self, results: &[ExtractionResult]) -> Result<()> {
        let path = Path::new(&self.output_path);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).with_context(|| {
                format!("Failed to create output directory: {}", parent.display())
            })?;
        }

        let is_new = !path.exists() || path.metadata().map(|m| m.len() == 0).unwrap_or(true);

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.output_path)
            .with_context(|| format!("Failed to open Markdown file: {}", self.output_path))?;

        if is_new {
            writeln!(file, "# Extraction Results\n")?;
        }

        for (i, result) in results.iter().enumerate() {
            writeln!(file, "---\n")?;
            writeln!(file, "## Result {}\n", i + 1)?;

            // Metadata table
            writeln!(file, "| Field | Value |")?;
            writeln!(file, "|-------|-------|")?;
            writeln!(file, "| result_id | `{}` |", result.result_id)?;
            writeln!(file, "| document_id | `{}` |", result.document_id)?;
            writeln!(file, "| chunk_index | {} |", result.chunk_index)?;
            writeln!(file, "| source_path | {} |", result.source_path)?;
            writeln!(file, "| format | {} |", result.format)?;
            writeln!(file, "| task | {} |", result.task)?;
            writeln!(
                file,
                "| model_used | {} |",
                result.model_used.as_deref().unwrap_or("—")
            )?;
            writeln!(
                file,
                "| is_valid | {} |",
                if result.is_valid { "✓ true" } else { "✗ false" }
            )?;
            writeln!(
                file,
                "| latency_ms | {} |",
                result
                    .latency_ms
                    .map(|ms| ms.to_string())
                    .unwrap_or_else(|| "—".to_string())
            )?;
            writeln!(file, "| created_at | {} |", result.created_at)?;
            writeln!(file)?;

            writeln!(file, "### Extracted data\n")?;
            match &result.structured_output {
                Some(v) if !v.is_null() => {
                    let body = render_schema_aware(&result.task, v)
                        .unwrap_or_else(|| json_value_to_markdown(v, 0));
                    writeln!(file, "{}", body.trim_end())?;
                    writeln!(file)?;
                }
                _ => {
                    writeln!(file, "_No structured output._\n")?;
                }
            }

            writeln!(file, "### Validation\n")?;
            if result.validation_errors.is_empty() {
                writeln!(file, "No errors.\n")?;
            } else {
                for err in &result.validation_errors {
                    writeln!(file, "- {}", err)?;
                }
                writeln!(file)?;
            }
        }

        Ok(())
    }
}

fn render_with_layout(task: &str, value: &Value) -> (&'static str, String) {
    if is_summary_payload(task, value) {
        return ("summary", render_summary_markdown(value));
    }
    if is_classification_payload(task, value) {
        return ("classification", render_classification_markdown(value));
    }
    if is_form_payload(task, value) {
        return ("form", render_form_markdown(value));
    }
    ("generic", json_value_to_markdown(value, 0))
}

fn is_summary_payload(task: &str, value: &Value) -> bool {
    let t = task.to_ascii_lowercase();
    if t.contains("summary") || t.contains("summar") {
        return true;
    }
    match value {
        Value::Object(m) => m.contains_key("summary") || m.contains_key("key_points") || m.contains_key("bullet_points"),
        _ => false,
    }
}

fn is_classification_payload(task: &str, value: &Value) -> bool {
    let t = task.to_ascii_lowercase();
    if t.contains("classif") || t.contains("sentiment") {
        return true;
    }
    match value {
        Value::Object(m) => m.contains_key("label") && (m.contains_key("confidence") || m.contains_key("secondary_labels") || m.contains_key("labels") || m.contains_key("scores")),
        _ => false,
    }
}

fn is_form_payload(task: &str, value: &Value) -> bool {
    let t = task.to_ascii_lowercase();
    if t.contains("form") {
        return true;
    }
    match value {
        Value::Object(m) => m.get("fields").map(|f| f.is_array()).unwrap_or(false),
        _ => false,
    }
}

fn render_summary_markdown(value: &Value) -> String {
    let mut out = String::new();
    if let Value::Object(m) = value {
        if let Some(title) = m.get("title").and_then(|v| v.as_str()) {
            if !title.trim().is_empty() {
                out.push_str(&format!("#### {}\n\n", title.trim()));
            }
        }
        if let Some(summary) = m.get("summary").and_then(|v| v.as_str()) {
            if !summary.trim().is_empty() {
                out.push_str(summary.trim());
                out.push_str("\n\n");
            }
        }
        let points = m.get("key_points").or_else(|| m.get("bullet_points"));
        if let Some(Value::Array(arr)) = points {
            if !arr.is_empty() {
                out.push_str("**Key points**\n");
                for p in arr {
                    out.push_str(&format!("- {}\n", scalar_for_list_item(p)));
                }
                out.push('\n');
            }
        }
        if let Some(wc) = m.get("word_count_estimate") {
            out.push_str(&format!("_Word count estimate: {}_\n", scalar_for_list_item(wc)));
        }
    }
    if out.trim().is_empty() {
        json_value_to_markdown(value, 0)
    } else {
        out
    }
}

fn render_classification_markdown(value: &Value) -> String {
    let mut out = String::new();
    if let Value::Object(m) = value {
        out.push_str("| Field | Value |\n|---|---|\n");
        if let Some(label) = m.get("label") {
            out.push_str(&format!("| Label | {} |\n", escape_table_cell(&scalar_for_list_item(label))));
        }
        if let Some(conf) = m.get("confidence") {
            out.push_str(&format!("| Confidence | {} |\n", escape_table_cell(&scalar_for_list_item(conf))));
        }
        out.push('\n');

        if let Some(reasoning) = m.get("reasoning").and_then(|v| v.as_str()) {
            if !reasoning.trim().is_empty() {
                out.push_str("**Reasoning**\n\n");
                out.push_str(reasoning.trim());
                out.push_str("\n\n");
            }
        }

        if let (Some(Value::Array(labels)), Some(Value::Array(scores))) = (m.get("labels"), m.get("scores")) {
            if !labels.is_empty() && labels.len() == scores.len() {
                out.push_str("**Candidate labels**\n\n");
                out.push_str("| Label | Score |\n|---|---|\n");
                for (l, s) in labels.iter().zip(scores.iter()) {
                    out.push_str(&format!(
                        "| {} | {} |\n",
                        escape_table_cell(&scalar_for_list_item(l)),
                        escape_table_cell(&scalar_for_list_item(s))
                    ));
                }
                out.push('\n');
            }
        }

        if let Some(Value::Array(sec)) = m.get("secondary_labels") {
            if !sec.is_empty() {
                out.push_str("**Secondary labels**\n");
                for item in sec {
                    out.push_str(&format!("- {}\n", scalar_for_list_item(item)));
                }
                out.push('\n');
            }
        }
    }
    if out.trim().is_empty() {
        json_value_to_markdown(value, 0)
    } else {
        out
    }
}

fn render_form_markdown(value: &Value) -> String {
    let mut out = String::new();
    if let Value::Object(m) = value {
        if let Some(form_type) = m.get("form_type").and_then(|v| v.as_str()) {
            if !form_type.trim().is_empty() {
                out.push_str(&format!("**Form type:** {}\n\n", form_type.trim()));
            }
        }
        if let Some(Value::Array(fields)) = m.get("fields") {
            if !fields.is_empty() && fields.iter().all(|x| x.is_object()) {
                out.push_str("| Field name | Value | Type | Page |\n|---|---|---|---|\n");
                for item in fields {
                    if let Value::Object(fm) = item {
                        let name = fm.get("field_name").map(scalar_for_list_item).unwrap_or_else(|| "—".to_string());
                        let val = fm.get("field_value").map(scalar_for_list_item).unwrap_or_else(|| "—".to_string());
                        let ty = fm.get("field_type").map(scalar_for_list_item).unwrap_or_else(|| "—".to_string());
                        let page = fm.get("page").map(scalar_for_list_item).unwrap_or_else(|| "—".to_string());
                        out.push_str(&format!(
                            "| {} | {} | {} | {} |\n",
                            escape_table_cell(&name),
                            escape_table_cell(&val),
                            escape_table_cell(&ty),
                            escape_table_cell(&page),
                        ));
                    }
                }
                out.push('\n');
            }
        }
    }
    if out.trim().is_empty() {
        json_value_to_markdown(value, 0)
    } else {
        out
    }
}

/// Render JSON-like structured output as readable Markdown (headings, lists, tables) — no ```json fence.
fn json_value_to_markdown(value: &Value, depth: usize) -> String {
    match value {
        Value::Null => "—".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        Value::Array(arr) => {
            if arr.is_empty() {
                return "_Empty._\n".to_string();
            }
            if arr.iter().all(|v| v.is_object()) {
                return objects_to_markdown_table(arr);
            }
            let mut out = String::new();
            for v in arr {
                let part = json_value_to_markdown(v, depth + 1);
                let line = part.trim_end();
                if line.contains('\n') {
                    out.push_str("- \n");
                    for l in line.lines() {
                        out.push_str(&format!("  {}\n", l));
                    }
                } else {
                    out.push_str(&format!("- {}\n", line));
                }
            }
            out
        }
        Value::Object(map) => {
            if map.is_empty() {
                return "_Empty._\n".to_string();
            }
            let mut out = String::new();
            for (k, v) in map {
                let heading = (3 + depth).min(6);
                match v {
                    Value::Object(inner) if !inner.is_empty() => {
                        out.push_str(&format!("\n{} {}\n\n", "#".repeat(heading), escape_heading_text(k)));
                        out.push_str(&json_value_to_markdown(v, depth + 1));
                    }
                    Value::Array(inner) => {
                        if !inner.is_empty() && inner.iter().all(|x| x.is_object()) {
                            out.push_str(&format!("\n**{}**\n\n", k));
                            out.push_str(&objects_to_markdown_table(inner));
                        } else {
                            out.push_str(&format!("\n**{}**\n\n", k));
                            out.push_str(&json_value_to_markdown(v, depth + 1));
                        }
                    }
                    _ => {
                        out.push_str(&format!(
                            "- **{}**: {}\n",
                            escape_heading_text(k),
                            scalar_for_list_item(v)
                        ));
                    }
                }
            }
            out
        }
    }
}

fn escape_heading_text(s: &str) -> String {
    s.replace('\n', " ")
}

fn scalar_for_list_item(v: &Value) -> String {
    match v {
        Value::String(s) => s.replace('\n', "  \n"),
        Value::Null => "—".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::Array(a) if a.is_empty() => "_Empty._".to_string(),
        Value::Object(o) if o.is_empty() => "_Empty._".to_string(),
        other => serde_json::to_string(other).unwrap_or_else(|_| other.to_string()),
    }
}

fn escape_table_cell(s: &str) -> String {
    s.replace('|', "\\|").replace('\n', " ")
}

fn objects_to_markdown_table(rows: &[Value]) -> String {
    let mut keys: Vec<String> = Vec::new();
    for row in rows {
        if let Value::Object(map) = row {
            for k in map.keys() {
                if !keys.contains(k) {
                    keys.push(k.clone());
                }
            }
        }
    }
    if keys.is_empty() {
        return String::new();
    }
    let mut lines: Vec<String> = Vec::new();
    lines.push(format!("| {} |", keys.join(" | ")));
    lines.push(format!("| {} |", keys.iter().map(|_| "---").collect::<Vec<_>>().join(" | ")));
    for row in rows {
        if let Value::Object(map) = row {
            let cells: Vec<String> = keys
                .iter()
                .map(|k| {
                    map.get(k)
                        .map(|v| escape_table_cell(&value_as_table_cell(v)))
                        .unwrap_or_default()
                })
                .collect();
            lines.push(format!("| {} |", cells.join(" | ")));
        }
    }
    lines.join("\n") + "\n"
}

fn value_as_table_cell(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => "—".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::Array(a) if a.is_empty() => "—".to_string(),
        Value::Object(o) if o.is_empty() => "—".to_string(),
        other => serde_json::to_string(other).unwrap_or_else(|_| other.to_string()),
    }
}

pub fn save_as_markdown(results: &[ExtractionResult], path: &str) -> Result<()> {
    MarkdownWriter::new(path).write(results)
}
