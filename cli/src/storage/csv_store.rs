use anyhow::{Context, Result};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::Path;

use super::ExtractionResult;

pub struct CSVWriter {
    pub output_path: String,
}

impl CSVWriter {
    pub fn new(output_path: &str) -> Self {
        Self { output_path: output_path.to_string() }
    }

    pub fn write(&self, results: &[ExtractionResult]) -> Result<()> {
        let path = Path::new(&self.output_path);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create output directory: {}", parent.display()))?;
        }

        // Collect all field names across all results (for dynamic headers)
        let mut all_keys: BTreeMap<String, ()> = BTreeMap::new();
        // Always include base fields
        for key in &["result_id", "document_id", "chunk_index", "source_path", "format", "task", "model_used", "is_valid", "validation_errors", "prompt_tokens", "completion_tokens"] {
            all_keys.insert(key.to_string(), ());
        }

        // Collect flattened output keys from all results
        let flattened: Vec<BTreeMap<String, String>> = results
            .iter()
            .map(|r| {
                let mut flat = BTreeMap::new();
                flat.insert("result_id".into(), r.result_id.to_string());
                flat.insert("document_id".into(), r.document_id.to_string());
                flat.insert("chunk_index".into(), r.chunk_index.to_string());
                flat.insert("source_path".into(), r.source_path.clone());
                flat.insert("format".into(), r.format.clone());
                flat.insert("task".into(), r.task.clone());
                flat.insert("model_used".into(), r.model_used.clone().unwrap_or_default());
                flat.insert("is_valid".into(), r.is_valid.to_string());
                flat.insert("validation_errors".into(), r.validation_errors.join("; "));
                flat.insert("prompt_tokens".into(), r.prompt_tokens.map(|n| n.to_string()).unwrap_or_default());
                flat.insert("completion_tokens".into(), r.completion_tokens.map(|n| n.to_string()).unwrap_or_default());

                // Flatten structured output
                if let Some(ref output) = r.structured_output {
                    flatten_value("output", output, &mut flat);
                }

                for key in flat.keys() {
                    all_keys.insert(key.clone(), ());
                }
                flat
            })
            .collect();

        let headers: Vec<String> = all_keys.into_keys().collect();

        let mut writer = csv::Writer::from_path(&self.output_path)
            .with_context(|| format!("Failed to create CSV file: {}", self.output_path))?;

        writer.write_record(&headers)?;

        for flat in &flattened {
            let row: Vec<String> = headers
                .iter()
                .map(|h| flat.get(h).cloned().unwrap_or_default())
                .collect();
            writer.write_record(&row)?;
        }

        writer.flush()?;
        Ok(())
    }
}

fn flatten_value(prefix: &str, value: &Value, out: &mut BTreeMap<String, String>) {
    match value {
        Value::Object(map) => {
            for (k, v) in map {
                let new_key = format!("{}.{}", prefix, k);
                flatten_value(&new_key, v, out);
            }
        }
        Value::Array(arr) => {
            let s = arr
                .iter()
                .map(|v| v.to_string())
                .collect::<Vec<_>>()
                .join(", ");
            out.insert(prefix.to_string(), s);
        }
        other => {
            out.insert(prefix.to_string(), other.to_string().trim_matches('"').to_string());
        }
    }
}

pub fn save_as_csv(results: &[ExtractionResult], path: &str) -> Result<()> {
    CSVWriter::new(path).write(results)
}
