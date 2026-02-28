use serde_json::Value;

use crate::inference::{GenerateRequest, LLMProvider, ProviderResult};
use super::{validate, ValidationResult};

pub struct RetryHandler {
    pub max_retries: usize,
}

impl RetryHandler {
    pub fn new(max_retries: usize) -> Self {
        Self { max_retries }
    }

    pub async fn validate_and_retry(
        &self,
        result: &ProviderResult,
        original_text: &str,
        schema: Option<&Value>,
        provider: &dyn LLMProvider,
        temperature: f32,
        max_tokens: usize,
    ) -> ValidationResult {
        let mut validation = validate(&result.content);

        if validation.is_valid {
            return validation;
        }

        // Retry with refined prompt
        for attempt in 0..self.max_retries {
            let refined_prompt = build_refined_prompt(original_text, &validation.errors, attempt);

            let mut req = GenerateRequest::new(&refined_prompt)
                .with_temperature(temperature)
                .with_max_tokens(max_tokens);

            if let Some(s) = schema {
                req = req.with_schema(s);
            }

            match provider.generate(req).await {
                Ok(retry_result) => {
                    validation = validate(&retry_result.content);
                    if validation.is_valid {
                        tracing::debug!(
                            attempt = attempt + 1,
                            "Validation succeeded on retry"
                        );
                        return validation;
                    }
                }
                Err(e) => {
                    tracing::warn!(error = %e, attempt = attempt + 1, "Retry attempt failed");
                    break;
                }
            }
        }

        tracing::warn!(
            retries = self.max_retries,
            "All retry attempts exhausted, returning invalid result"
        );
        validation
    }
}

fn build_refined_prompt(original_text: &str, errors: &[String], attempt: usize) -> String {
    let error_list = errors
        .iter()
        .enumerate()
        .map(|(i, e)| format!("  {}. {}", i + 1, e))
        .collect::<Vec<_>>()
        .join("\n");

    format!(
        "Your previous response could not be parsed as valid JSON (attempt {}).\n\
         Errors:\n{}\n\n\
         Please extract the structured data from the following text and return ONLY \
         valid JSON, no explanation, no markdown fences:\n\n{}",
        attempt + 1,
        error_list,
        original_text
    )
}
