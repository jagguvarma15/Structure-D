use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};

use crate::config::OpenAIConfig;
use super::provider::{default_system_prompt, GenerateRequest, LLMProvider, ProviderResult};

pub struct OpenAIProvider {
    client: Client,
    config: OpenAIConfig,
}

impl OpenAIProvider {
    pub fn new(config: OpenAIConfig) -> Result<Self> {
        let api_key = config
            .api_key
            .clone()
            .or_else(|| std::env::var("OPENAI_API_KEY").ok())
            .context("OpenAI API key not set. Provide via config or OPENAI_API_KEY env var.")?;

        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert(
            "Authorization",
            format!("Bearer {}", api_key).parse()?,
        );
        headers.insert("Content-Type", "application/json".parse()?);

        let client = Client::builder()
            .default_headers(headers)
            .build()?;

        Ok(Self { client, config })
    }
}

#[async_trait]
impl LLMProvider for OpenAIProvider {
    fn name(&self) -> &str {
        "openai"
    }

    async fn generate(&self, req: GenerateRequest<'_>) -> Result<ProviderResult> {
        let model = req.model.unwrap_or(&self.config.model);

        let system_content = match req.system_prompt {
            Some(s) => s.to_string(),
            None => match req.schema {
                Some(schema) => default_system_prompt(schema),
                None => "You are a helpful assistant.".to_string(),
            },
        };

        let mut body = json!({
            "model": model,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "messages": [
                { "role": "system", "content": system_content },
                { "role": "user", "content": req.prompt }
            ]
        });

        // Request structured JSON output when a schema is provided
        if let Some(schema) = req.schema {
            body["response_format"] = json!({
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_result",
                    "strict": true,
                    "schema": schema
                }
            });
        }

        let url = format!("{}/chat/completions", self.config.base_url.trim_end_matches('/'));
        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .context("OpenAI request failed")?;

        let status = resp.status();
        let text = resp.text().await?;

        if !status.is_success() {
            bail!("OpenAI API error ({}): {}", status, text);
        }

        let data: Value = serde_json::from_str(&text).context("OpenAI: invalid JSON response")?;

        let content = data["choices"][0]["message"]["content"]
            .as_str()
            .context("OpenAI: missing content in response")?
            .to_string();

        let finish_reason = data["choices"][0]["finish_reason"]
            .as_str()
            .map(|s| s.to_string());

        let prompt_tokens = data["usage"]["prompt_tokens"].as_u64().map(|n| n as u32);
        let completion_tokens = data["usage"]["completion_tokens"].as_u64().map(|n| n as u32);

        Ok(ProviderResult {
            content,
            model: model.to_string(),
            prompt_tokens,
            completion_tokens,
            finish_reason,
        })
    }
}
