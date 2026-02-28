use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};

use crate::config::OllamaConfig;
use super::provider::{default_system_prompt, GenerateRequest, LLMProvider, ProviderResult};

pub struct OllamaProvider {
    client: Client,
    config: OllamaConfig,
}

impl OllamaProvider {
    pub fn new(config: OllamaConfig) -> Self {
        Self { client: Client::new(), config }
    }
}

#[async_trait]
impl LLMProvider for OllamaProvider {
    fn name(&self) -> &str {
        "ollama"
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
            "stream": false,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens
            },
            "messages": [
                { "role": "system", "content": system_content },
                { "role": "user", "content": req.prompt }
            ]
        });

        // Ollama supports format: "json" for JSON-constrained output
        if req.schema.is_some() {
            body["format"] = json!("json");
        }

        let url = format!("{}/api/chat", self.config.base_url.trim_end_matches('/'));

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .context("Ollama request failed")?;

        let status = resp.status();
        let text = resp.text().await?;

        if !status.is_success() {
            bail!("Ollama API error ({}): {}", status, text);
        }

        let data: Value = serde_json::from_str(&text).context("Ollama: invalid JSON response")?;

        let content = data["message"]["content"]
            .as_str()
            .context("Ollama: missing content in response")?
            .to_string();

        let finish_reason = data["done_reason"].as_str().map(|s| s.to_string());
        let prompt_tokens = data["prompt_eval_count"].as_u64().map(|n| n as u32);
        let completion_tokens = data["eval_count"].as_u64().map(|n| n as u32);

        Ok(ProviderResult {
            content,
            model: model.to_string(),
            prompt_tokens,
            completion_tokens,
            finish_reason,
        })
    }
}
