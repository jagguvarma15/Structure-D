use anyhow::Result;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderResult {
    pub content: String,
    pub model: String,
    pub prompt_tokens: Option<u32>,
    pub completion_tokens: Option<u32>,
    pub finish_reason: Option<String>,
}

#[derive(Debug, Clone)]
pub struct GenerateRequest<'a> {
    pub prompt: &'a str,
    pub schema: Option<&'a Value>,
    pub system_prompt: Option<&'a str>,
    pub temperature: f32,
    pub max_tokens: usize,
    pub model: Option<&'a str>,
}

impl<'a> GenerateRequest<'a> {
    pub fn new(prompt: &'a str) -> Self {
        Self {
            prompt,
            schema: None,
            system_prompt: None,
            temperature: 0.0,
            max_tokens: 2048,
            model: None,
        }
    }

    pub fn with_schema(mut self, schema: &'a Value) -> Self {
        self.schema = Some(schema);
        self
    }

    pub fn with_system(mut self, system: &'a str) -> Self {
        self.system_prompt = Some(system);
        self
    }

    pub fn with_temperature(mut self, temp: f32) -> Self {
        self.temperature = temp;
        self
    }

    pub fn with_max_tokens(mut self, max: usize) -> Self {
        self.max_tokens = max;
        self
    }

    pub fn with_model(mut self, model: &'a str) -> Self {
        self.model = Some(model);
        self
    }
}

#[async_trait]
#[allow(dead_code)]
pub trait LLMProvider: Send + Sync {
    fn name(&self) -> &str;

    /// Generate a structured response constrained to the given JSON schema.
    async fn generate(&self, req: GenerateRequest<'_>) -> Result<ProviderResult>;

    /// Generate plain text (no schema constraint).
    async fn generate_text(&self, req: GenerateRequest<'_>) -> Result<String> {
        Ok(self.generate(req).await?.content)
    }
}

/// Build the default extraction system prompt.
pub fn default_system_prompt(schema: &Value) -> String {
    format!(
        "You are a precise data extraction assistant. \
         Extract information from the provided text and return ONLY valid JSON \
         matching this schema:\n\n{}\n\n\
         Return only the JSON object, no explanation, no markdown fences.",
        serde_json::to_string_pretty(schema).unwrap_or_default()
    )
}
