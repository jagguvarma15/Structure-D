use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};

use crate::config::VLLMConfig;
use super::provider::{default_system_prompt, GenerateRequest, LLMProvider, ProviderResult};

pub struct VLLMProvider {
    client: Client,
    config: VLLMConfig,
}

impl VLLMProvider {
    pub fn new(config: VLLMConfig) -> Self {
        Self { client: Client::new(), config }
    }
}

#[async_trait]
impl LLMProvider for VLLMProvider {
    fn name(&self) -> &str {
        "vllm"
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

        // vLLM guided decoding: pass JSON schema as guided_json
        if let Some(schema) = req.schema {
            body["guided_json"] = schema.clone();
            // Also set response_format for compatibility with some vLLM versions
            body["response_format"] = json!({ "type": "json_object" });
        }

        let url = format!(
            "{}/chat/completions",
            self.config.api_base.trim_end_matches('/')
        );

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .context("vLLM request failed")?;

        let status = resp.status();
        let text = resp.text().await?;

        if !status.is_success() {
            bail!("vLLM API error ({}): {}", status, text);
        }

        let data: Value = serde_json::from_str(&text).context("vLLM: invalid JSON response")?;

        let content = data["choices"][0]["message"]["content"]
            .as_str()
            .context("vLLM: missing content in response")?
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
