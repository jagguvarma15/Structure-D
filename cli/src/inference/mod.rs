pub mod anthropic;
pub mod gemini;
pub mod ollama;
pub mod openai;
pub mod provider;
pub mod vllm;

use anyhow::{bail, Result};

pub use provider::{GenerateRequest, LLMProvider, ProviderResult};

use crate::config::InferenceConfig;
use anthropic::AnthropicProvider;
use gemini::GeminiProvider;
use ollama::OllamaProvider;
use openai::OpenAIProvider;
use vllm::VLLMProvider;

/// Factory function: returns a boxed provider based on config.provider string.
pub fn get_provider(config: &InferenceConfig) -> Result<Box<dyn LLMProvider>> {
    match config.provider.as_str() {
        "vllm" => Ok(Box::new(VLLMProvider::new(config.vllm.clone()))),
        "openai" => Ok(Box::new(OpenAIProvider::new(config.openai.clone())?)),
        "anthropic" => Ok(Box::new(AnthropicProvider::new(config.anthropic.clone())?)),
        "gemini" => Ok(Box::new(GeminiProvider::new(config.gemini.clone())?)),
        "ollama" => Ok(Box::new(OllamaProvider::new(config.ollama.clone()))),
        other => bail!(
            "Unknown provider '{}'. Valid options: vllm, openai, anthropic, gemini, ollama",
            other
        ),
    }
}
