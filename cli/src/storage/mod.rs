pub mod csv_store;
pub mod jsonl;
pub mod markdown;
pub mod parquet_store;
pub mod tabular;

use serde::{Deserialize, Serialize};
use uuid::Uuid;


#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractionResult {
    pub result_id: Uuid,
    pub document_id: Uuid,
    pub chunk_index: usize,
    pub source_path: String,
    pub format: String,
    pub task: String,
    pub model_used: Option<String>,
    pub is_valid: bool,
    pub structured_output: Option<serde_json::Value>,
    pub validation_errors: Vec<String>,
    pub prompt_tokens: Option<u32>,
    pub completion_tokens: Option<u32>,
    pub latency_ms: Option<u64>,
    pub created_at: String,
}

impl ExtractionResult {
    pub fn new(
        document_id: Uuid,
        chunk_index: usize,
        source_path: String,
        format: String,
        task: String,
    ) -> Self {
        Self {
            result_id: Uuid::new_v4(),
            document_id,
            chunk_index,
            source_path,
            format,
            task,
            model_used: None,
            is_valid: false,
            structured_output: None,
            validation_errors: vec![],
            prompt_tokens: None,
            completion_tokens: None,
            latency_ms: None,
            created_at: chrono::Utc::now().to_rfc3339(),
        }
    }
}
