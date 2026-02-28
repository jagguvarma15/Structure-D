use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};

use crate::config::GeminiConfig;
use super::provider::{default_system_prompt, GenerateRequest, LLMProvider, ProviderResult};

const GEMINI_API_BASE: &str = "https://generativelanguage.googleapis.com/v1beta/models";

pub struct GeminiProvider {
    client: Client,
    config: GeminiConfig,
    api_key: String,
}

impl GeminiProvider {
    pub fn new(config: GeminiConfig) -> Result<Self> {
        let api_key = config
            .api_key
            .clone()
            .or_else(|| std::env::var("GEMINI_API_KEY").ok())
            .or_else(|| std::env::var("GOOGLE_API_KEY").ok())
            .context("Gemini API key not set. Provide via config or GEMINI_API_KEY env var.")?;

        Ok(Self { client: Client::new(), config, api_key })
    }
}

#[async_trait]
impl LLMProvider for GeminiProvider {
    fn name(&self) -> &str {
        "gemini"
    }

    async fn generate(&self, req: GenerateRequest<'_>) -> Result<ProviderResult> {
        let model = req.model.unwrap_or(&self.config.model);

        let url = format!(
            "{}/{}:generateContent?key={}",
            GEMINI_API_BASE, model, self.api_key
        );

        let system_instruction = match req.system_prompt {
            Some(s) => s.to_string(),
            None => match req.schema {
                Some(schema) => default_system_prompt(schema),
                None => String::new(),
            },
        };

        let mut body = json!({
            "contents": [
                {
                    "role": "user",
                    "parts": [{ "text": req.prompt }]
                }
            ],
            "generationConfig": {
                "temperature": req.temperature,
                "maxOutputTokens": req.max_tokens
            }
        });

        if !system_instruction.is_empty() {
            body["systemInstruction"] = json!({
                "parts": [{ "text": system_instruction }]
            });
        }

        // Structured JSON output
        if req.schema.is_some() {
            body["generationConfig"]["responseMimeType"] = json!("application/json");
        }

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .context("Gemini request failed")?;

        let status = resp.status();
        let text = resp.text().await?;

        if !status.is_success() {
            bail!("Gemini API error ({}): {}", status, text);
        }

        let data: Value = serde_json::from_str(&text).context("Gemini: invalid JSON response")?;

        let content = data["candidates"][0]["content"]["parts"][0]["text"]
            .as_str()
            .context("Gemini: missing text in response")?
            .to_string();

        let finish_reason = data["candidates"][0]["finishReason"]
            .as_str()
            .map(|s| s.to_string());

        let prompt_tokens = data["usageMetadata"]["promptTokenCount"]
            .as_u64()
            .map(|n| n as u32);
        let completion_tokens = data["usageMetadata"]["candidatesTokenCount"]
            .as_u64()
            .map(|n| n as u32);

        Ok(ProviderResult {
            content,
            model: model.to_string(),
            prompt_tokens,
            completion_tokens,
            finish_reason,
        })
    }
}
