use thiserror::Error;

#[derive(Debug, Error)]
pub enum StructureDError {
    #[error("Configuration error: {0}")]
    Config(String),

    #[error("Ingestion error: {0}")]
    Ingestion(String),

    #[error("Inference error: {0}")]
    Inference(String),

    #[error("Provider error ({provider}): {message}")]
    Provider { provider: String, message: String },

    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("Validation error: {0}")]
    Validation(String),

    #[error("Storage error: {0}")]
    Storage(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),

    #[error("Unsupported format: {0}")]
    UnsupportedFormat(String),

    #[error("Schema not found: {0}")]
    SchemaNotFound(String),
}

pub type Result<T> = std::result::Result<T, anyhow::Error>;
