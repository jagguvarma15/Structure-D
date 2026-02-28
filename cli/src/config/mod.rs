use anyhow::{Context, Result};
use figment::{
    providers::{Env, Format, Serialized, Yaml},
    Figment,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ── Ingestion ─────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct ConnectorConfig {
    pub r#type: String,
    pub base_path: Option<String>,
}

impl Default for ConnectorConfig {
    fn default() -> Self {
        Self { r#type: "local".into(), base_path: None }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct IngestionConfig {
    pub default_parser: String,
    pub ocr_engine: String,
    pub max_file_size_mb: u64,
    pub connector: ConnectorConfig,
}

impl Default for IngestionConfig {
    fn default() -> Self {
        Self {
            default_parser: "auto".into(),
            ocr_engine: "tesseract".into(),
            max_file_size_mb: 100,
            connector: ConnectorConfig::default(),
        }
    }
}

// ── Preprocessing ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct ChunkingConfig {
    pub strategy: String,
    pub max_tokens: usize,
    pub overlap: usize,
    pub heading_levels: Vec<u8>,
}

impl Default for ChunkingConfig {
    fn default() -> Self {
        Self {
            strategy: "semantic".into(),
            max_tokens: 1024,
            overlap: 128,
            heading_levels: vec![1, 2, 3],
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct PreprocessingConfig {
    pub normalize_unicode: bool,
    pub strip_boilerplate: bool,
    pub collapse_whitespace: bool,
    pub chunking: ChunkingConfig,
}

impl Default for PreprocessingConfig {
    fn default() -> Self {
        Self {
            normalize_unicode: true,
            strip_boilerplate: true,
            collapse_whitespace: true,
            chunking: ChunkingConfig::default(),
        }
    }
}

// ── Inference providers ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct VLLMConfig {
    pub api_base: String,
    pub model: String,
    pub structured_output_backend: String,
    pub gpu_memory_utilization: f32,
    pub max_model_len: Option<usize>,
}

impl Default for VLLMConfig {
    fn default() -> Self {
        Self {
            api_base: "http://localhost:8000/v1".into(),
            model: "meta-llama/Meta-Llama-3.1-8B-Instruct".into(),
            structured_output_backend: "auto".into(),
            gpu_memory_utilization: 0.9,
            max_model_len: None,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct OpenAIConfig {
    pub model: String,
    pub api_key: Option<String>,
    pub base_url: String,
}

impl Default for OpenAIConfig {
    fn default() -> Self {
        Self {
            model: "gpt-4o-mini".into(),
            api_key: None,
            base_url: "https://api.openai.com/v1".into(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct AnthropicConfig {
    pub model: String,
    pub api_key: Option<String>,
}

impl Default for AnthropicConfig {
    fn default() -> Self {
        Self {
            model: "claude-sonnet-4-6".into(),
            api_key: None,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct GeminiConfig {
    pub model: String,
    pub api_key: Option<String>,
}

impl Default for GeminiConfig {
    fn default() -> Self {
        Self {
            model: "gemini-2.0-flash".into(),
            api_key: None,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct OllamaConfig {
    pub base_url: String,
    pub model: String,
}

impl Default for OllamaConfig {
    fn default() -> Self {
        Self {
            base_url: "http://localhost:11434".into(),
            model: "llama3.1".into(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct BatchConfig {
    pub max_batch_size: usize,
    pub max_concurrent: usize,
}

impl Default for BatchConfig {
    fn default() -> Self {
        Self { max_batch_size: 32, max_concurrent: 4 }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct InferenceConfig {
    pub provider: String,
    pub vllm: VLLMConfig,
    pub openai: OpenAIConfig,
    pub anthropic: AnthropicConfig,
    pub gemini: GeminiConfig,
    pub ollama: OllamaConfig,
    pub batch: BatchConfig,
    pub temperature: f32,
    pub max_tokens: usize,
    pub system_prompt: Option<String>,
}

impl Default for InferenceConfig {
    fn default() -> Self {
        Self {
            provider: "vllm".into(),
            vllm: VLLMConfig::default(),
            openai: OpenAIConfig::default(),
            anthropic: AnthropicConfig::default(),
            gemini: GeminiConfig::default(),
            ollama: OllamaConfig::default(),
            batch: BatchConfig::default(),
            temperature: 0.0,
            max_tokens: 2048,
            system_prompt: None,
        }
    }
}

// ── Validation ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct ValidationConfig {
    pub strict: bool,
    pub max_retries: usize,
    pub retry_with_refined_prompt: bool,
    pub fallback_to_regex: bool,
}

impl Default for ValidationConfig {
    fn default() -> Self {
        Self {
            strict: false,
            max_retries: 3,
            retry_with_refined_prompt: true,
            fallback_to_regex: true,
        }
    }
}

// ── Storage ───────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct StorageConfig {
    pub default_format: String,
    pub output_dir: String,
}

impl Default for StorageConfig {
    fn default() -> Self {
        Self {
            default_format: "jsonl".into(),
            output_dir: "./output".into(),
        }
    }
}

// ── API ───────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct APIConfig {
    pub host: String,
    pub port: u16,
}

impl Default for APIConfig {
    fn default() -> Self {
        Self { host: "0.0.0.0".into(), port: 7433 }
    }
}

// ── Monitoring ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct MonitoringConfig {
    pub log_level: String,
    pub prometheus_enabled: bool,
    pub prometheus_port: u16,
}

impl Default for MonitoringConfig {
    fn default() -> Self {
        Self {
            log_level: "info".into(),
            prometheus_enabled: false,
            prometheus_port: 9090,
        }
    }
}

// ── Root settings ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Deserialize, Serialize, Default)]
#[serde(default)]
pub struct Settings {
    pub ingestion: IngestionConfig,
    pub preprocessing: PreprocessingConfig,
    pub inference: InferenceConfig,
    pub validation: ValidationConfig,
    pub storage: StorageConfig,
    pub api: APIConfig,
    pub monitoring: MonitoringConfig,
}

impl Settings {
    /// Load config from (in order of priority, highest last wins):
    ///   1. Built-in defaults
    ///   2. `configs/default.yaml` in the repo root (if found)
    ///   3. `~/.structure-d/config.yaml` (user config)
    ///   4. Path provided via `--config` flag
    ///   5. Environment variables prefixed with `SD_` using `__` as nested delimiter
    pub fn load(config_path: Option<&PathBuf>) -> Result<Self> {
        let mut figment = Figment::from(Serialized::defaults(Settings::default()));

        // Rust-specific config (separate from configs/default.yaml which is for Python)
        let rust_config = PathBuf::from("configs/default-rust.yaml");
        if rust_config.exists() {
            figment = figment.merge(Yaml::file(&rust_config));
        }

        // User home config: ~/.structure-d/config.yaml
        if let Some(home) = dirs::home_dir() {
            let user_config = home.join(".structure-d").join("config.yaml");
            if user_config.exists() {
                figment = figment.merge(Yaml::file(&user_config));
            }
        }

        // Explicit --config override
        if let Some(path) = config_path {
            if !path.exists() {
                anyhow::bail!("Config file not found: {}", path.display());
            }
            figment = figment.merge(Yaml::file(path));
        }

        // Environment variables: SD_INFERENCE__PROVIDER → inference.provider
        // e.g. SD_INFERENCE__PROVIDER=openai sets inference.provider
        figment = figment.merge(Env::prefixed("SD_").split("__"));

        figment.extract().context("Failed to parse configuration")
    }
}
