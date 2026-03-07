use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde_json::{json, Value};
use std::collections::HashSet;

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

        // Request structured JSON output when a schema is provided.
        // OpenAI strict mode requires every object to have additionalProperties:false
        // and all property keys listed in "required". We normalise the schema here.
        if let Some(schema) = req.schema {
            let strict_schema = normalize_for_strict(schema);
            body["response_format"] = json!({
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_result",
                    "strict": true,
                    "schema": strict_schema
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

// ── Schema normalisation for OpenAI strict mode ───────────────────────────────
//
// OpenAI's `json_schema` response format with `"strict": true` requires:
//   1. `"additionalProperties": false` on every `"type": "object"` node
//   2. Every property key listed in `"required"` (optional → nullable type)
//
// This function recursively transforms any JSON Schema to satisfy those rules.

/// Recursively normalise a JSON Schema so it is accepted by OpenAI strict mode.
fn normalize_for_strict(schema: &Value) -> Value {
    match schema {
        Value::Object(map) => {
            let is_object = map.get("type").and_then(|t| t.as_str()) == Some("object");

            // Collect property keys already marked as required
            let required_set: HashSet<&str> = map
                .get("required")
                .and_then(|r| r.as_array())
                .map(|arr| arr.iter().filter_map(|v| v.as_str()).collect())
                .unwrap_or_default();

            let mut out = serde_json::Map::new();

            for (k, v) in map {
                match k.as_str() {
                    // Force additionalProperties to false — dynamic keys are not
                    // allowed in strict mode regardless of the original value.
                    "additionalProperties" => {
                        out.insert(k.clone(), Value::Bool(false));
                    }
                    // Recursively normalise each property schema.
                    // Properties not in "required" are made nullable so OpenAI
                    // won't reject responses where the LLM omits that field.
                    "properties" if is_object => {
                        if let Value::Object(props) = v {
                            let normalised: serde_json::Map<String, Value> = props
                                .iter()
                                .map(|(pk, pv)| {
                                    let norm = normalize_for_strict(pv);
                                    let final_v = if required_set.contains(pk.as_str()) {
                                        norm
                                    } else {
                                        make_nullable(norm)
                                    };
                                    (pk.clone(), final_v)
                                })
                                .collect();
                            out.insert(k.clone(), Value::Object(normalised));
                        } else {
                            out.insert(k.clone(), v.clone());
                        }
                    }
                    // Recurse into array items
                    "items" => {
                        out.insert(k.clone(), normalize_for_strict(v));
                    }
                    // Recurse into schema combinators
                    "anyOf" | "oneOf" | "allOf" => {
                        if let Value::Array(arr) = v {
                            out.insert(
                                k.clone(),
                                Value::Array(arr.iter().map(normalize_for_strict).collect()),
                            );
                        } else {
                            out.insert(k.clone(), v.clone());
                        }
                    }
                    _ => {
                        out.insert(k.clone(), v.clone());
                    }
                }
            }

            // For object nodes: guarantee additionalProperties:false and full required list
            if is_object {
                out.entry("additionalProperties".to_string())
                    .or_insert(Value::Bool(false));

                if let Some(Value::Object(props)) = out.get("properties") {
                    let all_keys: Vec<Value> =
                        props.keys().map(|k| Value::String(k.clone())).collect();
                    if !all_keys.is_empty() {
                        out.insert("required".to_string(), Value::Array(all_keys));
                    }
                }
            }

            Value::Object(out)
        }
        Value::Array(arr) => Value::Array(arr.iter().map(normalize_for_strict).collect()),
        other => other.clone(),
    }
}

/// Extend a schema to also accept `null`, turning a required-but-optional
/// property into one the LLM can safely omit.
fn make_nullable(schema: Value) -> Value {
    match &schema {
        Value::Object(map) => {
            if let Some(Value::String(t)) = map.get("type") {
                if t != "null" {
                    let mut new_map = map.clone();
                    new_map.insert("type".to_string(), json!([t, "null"]));
                    return Value::Object(new_map);
                }
            }
            schema
        }
        _ => schema,
    }
}
