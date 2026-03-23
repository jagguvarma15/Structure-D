//! Shared tabular flattening for CSV and Parquet writers.

use std::collections::BTreeMap;

use serde_json::Value;

use super::ExtractionResult;

const BASE_KEYS: &[&str] = &[
    "result_id",
    "document_id",
    "chunk_index",
    "source_path",
    "format",
    "task",
    "model_used",
    "is_valid",
    "validation_errors",
    "prompt_tokens",
    "completion_tokens",
];

/// Headers (sorted / stable order) and one string row per [`ExtractionResult`].
pub fn tabular_headers_and_rows(results: &[ExtractionResult]) -> (Vec<String>, Vec<Vec<String>>) {
    let mut all_keys: BTreeMap<String, ()> = BTreeMap::new();
    for key in BASE_KEYS {
        all_keys.insert((*key).to_string(), ());
    }

    if results.is_empty() {
        let headers: Vec<String> = all_keys.into_keys().collect();
        return (headers, Vec::new());
    }

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
            flat.insert(
                "prompt_tokens".into(),
                r.prompt_tokens.map(|n| n.to_string()).unwrap_or_default(),
            );
            flat.insert(
                "completion_tokens".into(),
                r.completion_tokens.map(|n| n.to_string()).unwrap_or_default(),
            );

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

    let rows: Vec<Vec<String>> = flattened
        .iter()
        .map(|flat| {
            headers
                .iter()
                .map(|h| flat.get(h).cloned().unwrap_or_default())
                .collect()
        })
        .collect();

    (headers, rows)
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
            out.insert(
                prefix.to_string(),
                other.to_string().trim_matches('"').to_string(),
            );
        }
    }
}
