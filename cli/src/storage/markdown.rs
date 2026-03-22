use anyhow::{Context, Result};
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

            // Structured output
            writeln!(file, "### Structured Output\n")?;
            let output_json = match &result.structured_output {
                Some(v) => serde_json::to_string_pretty(v).unwrap_or_else(|_| v.to_string()),
                None => "null".to_string(),
            };
            writeln!(file, "```json")?;
            writeln!(file, "{}", output_json)?;
            writeln!(file, "```\n")?;

            // Validation
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

pub fn save_as_markdown(results: &[ExtractionResult], path: &str) -> Result<()> {
    MarkdownWriter::new(path).write(results)
}
