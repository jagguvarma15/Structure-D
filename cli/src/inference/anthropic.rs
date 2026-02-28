use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};

use crate::config::AnthropicConfig;
use super::provider::{GenerateRequest, LLMProvider, ProviderResult};

const ANTHROPIC_API_URL: &str = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION: &str = "2023-06-01";

pub struct AnthropicProvider {
    client: Client,
    config: AnthropicConfig,
}

impl AnthropicProvider {
    pub fn new(config: AnthropicConfig) -> Result<Self> {
        let api_key = config
            .api_key
            .clone()
            .or_else(|| std::env::var("ANTHROPIC_API_KEY").ok())
            .context("Anthropic API key not set. Provide via config or ANTHROPIC_API_KEY env var.")?;

        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert("x-api-key", api_key.parse()?);
        headers.insert("anthropic-version", ANTHROPIC_VERSION.parse()?);
        headers.insert("Content-Type", "application/json".parse()?);

        let client = Client::builder()
            .default_headers(headers)
            .build()?;

        Ok(Self { client, config })
    }
}

#[async_trait]
impl LLMProvider for AnthropicProvider {
    fn name(&self) -> &str {
        "anthropic"
    }

    async fn generate(&self, req: GenerateRequest<'_>) -> Result<ProviderResult> {
        let model = req.model.unwrap_or(&self.config.model);

        let mut body = json!({
            "model": model,
            "max_tokens": req.max_tokens,
            "messages": [
                { "role": "user", "content": req.prompt }
            ]
        });

        if let Some(s) = req.system_prompt {
            body["system"] = json!(s);
        }

        // Use tool_use with JSON schema for structured output
        if let Some(schema) = req.schema {
            body["tools"] = json!([{
                "name": "extract_data",
                "description": "Extract structured data from the provided text",
                "input_schema": schema
            }]);
            body["tool_choice"] = json!({ "type": "tool", "name": "extract_data" });
        }

        let resp = self
            .client
            .post(ANTHROPIC_API_URL)
            .json(&body)
            .send()
            .await
            .context("Anthropic request failed")?;

        let status = resp.status();
        let text = resp.text().await?;

        if !status.is_success() {
            bail!("Anthropic API error ({}): {}", status, text);
        }

        let data: Value = serde_json::from_str(&text).context("Anthropic: invalid JSON response")?;

        // Extract content: tool_use block has the JSON in "input", text block has raw text
        let content = if let Some(blocks) = data["content"].as_array() {
            let mut result = String::new();
            for block in blocks {
                match block["type"].as_str() {
                    Some("tool_use") => {
                        result = serde_json::to_string(&block["input"])
                            .unwrap_or_default();
                        break;
                    }
                    Some("text") => {
                        result = block["text"].as_str().unwrap_or_default().to_string();
                    }
                    _ => {}
                }
            }
            result
        } else {
            bail!("Anthropic: unexpected response format");
        };

        let finish_reason = data["stop_reason"].as_str().map(|s| s.to_string());
        let prompt_tokens = data["usage"]["input_tokens"].as_u64().map(|n| n as u32);
        let completion_tokens = data["usage"]["output_tokens"].as_u64().map(|n| n as u32);

        Ok(ProviderResult {
            content,
            model: model.to_string(),
            prompt_tokens,
            completion_tokens,
            finish_reason,
        })
    }
}
