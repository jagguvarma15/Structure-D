use anyhow::Result;
use futures::future::join_all;
use indicatif::{ProgressBar, ProgressStyle};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::Semaphore;
use tracing::{info, warn};

use crate::config::Settings;
use crate::ingestion::{parse_file, DocumentFormat, ParsedDocument};
use crate::inference::{get_provider, GenerateRequest, LLMProvider};
use crate::preprocessing::normalize_text;
use crate::storage::ExtractionResult;
use crate::validation::retry::RetryHandler;

pub struct Pipeline {
    schema: Value,
    task: String,
    config: Arc<Settings>,
    provider: Arc<Box<dyn LLMProvider>>,
}

impl Pipeline {
    pub fn new(schema: Value, task: &str, config: Settings) -> Result<Self> {
        let provider = get_provider(&config.inference)?;
        Ok(Self {
            schema,
            task: task.to_string(),
            config: Arc::new(config),
            provider: Arc::new(provider),
        })
    }

    pub fn with_provider(
        schema: Value,
        task: &str,
        config: Settings,
        provider: Box<dyn LLMProvider>,
    ) -> Self {
        Self {
            schema,
            task: task.to_string(),
            config: Arc::new(config),
            provider: Arc::new(provider),
        }
    }

    /// Process a single file through the pipeline:
    ///
    /// 1. **Ingest**      — auto-detect format and parse (code-controlled)
    /// 2. **Preprocess**  — normalise unicode, strip boilerplate (code-controlled)
    /// 3. **Aggregate**   — join the full document content; trim to context window
    /// 4. **Structure**   — one LLM call with all content + schema → structured JSON
    /// 5. **Validate**    — parse + retry if the LLM output is malformed
    /// 6. **Return**      — single [`ExtractionResult`] for the whole document
    pub async fn run(
        &self,
        file_path: &Path,
        parser_override: Option<&str>,
        model: Option<&str>,
    ) -> Result<Vec<ExtractionResult>> {
        let start = Instant::now();

        // ── Stage 1: Ingest (code-controlled) ────────────────────────────────
        let doc = parse_file(file_path, parser_override)?;
        info!(
            path = %file_path.display(),
            format = %doc.format,
            chars = doc.content.len(),
            "Ingestion complete"
        );

        self.run_on_document(doc, model, start).await
    }

    async fn run_on_document(
        &self,
        doc: ParsedDocument,
        model: Option<&str>,
        start: Instant,
    ) -> Result<Vec<ExtractionResult>> {
        let pre_cfg = &self.config.preprocessing;
        let inf_cfg = &self.config.inference;
        let val_cfg = &self.config.validation;

        // ── Stage 2: Preprocess (code-controlled) ─────────────────────────────
        let normalized = normalize_text(
            &doc.content,
            pre_cfg.normalize_unicode,
            pre_cfg.strip_boilerplate,
            pre_cfg.collapse_whitespace,
        );

        // ── Stage 3: Aggregate — trim full content to context window ──────────
        // Reserve ~512 tokens for the system prompt + schema overhead.
        let content_budget = inf_cfg.max_tokens.saturating_sub(512);
        let content = trim_to_context(&normalized, content_budget);

        // Capture fields we need after doc is consumed below.
        let doc_id       = doc.id;  // Uuid is Copy
        let source_path  = doc.source_path.clone();
        let format_label = doc.format.to_string();
        let doc_format   = doc.format.clone();

        // ── Model selection ───────────────────────────────────────────────────
        let model_name = model
            .map(|s| s.to_string())
            .unwrap_or_else(|| match inf_cfg.provider.as_str() {
                "openai"    => inf_cfg.openai.model.clone(),
                "anthropic" => inf_cfg.anthropic.model.clone(),
                "gemini"    => inf_cfg.gemini.model.clone(),
                "ollama"    => inf_cfg.ollama.model.clone(),
                _           => inf_cfg.vllm.model.clone(),
            });

        // ── Stage 4: Single LLM call — structure the whole document ───────────
        let system = build_system_prompt(&self.schema);
        let prompt = build_extraction_prompt(&doc_format, &content);

        let req = GenerateRequest::new(&prompt)
            .with_system(&system)
            .with_schema(&self.schema)
            .with_temperature(inf_cfg.temperature)
            .with_max_tokens(inf_cfg.max_tokens)
            .with_model(&model_name);

        // Indeterminate spinner (one call, unknown duration)
        let spinner = ProgressBar::new_spinner();
        spinner.set_style(
            ProgressStyle::with_template("{spinner:.cyan} {msg}")
                .unwrap()
                .tick_strings(&["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]),
        );
        spinner.set_message(format!("Structuring {format_label} with {model_name}…"));
        spinner.enable_steady_tick(std::time::Duration::from_millis(80));

        let mut result = ExtractionResult::new(
            doc_id,
            0, // whole-document extraction: chunk_index = 0
            source_path,
            format_label.clone(),
            self.task.clone(),
        );
        result.model_used = Some(model_name.clone());

        let call_start = Instant::now();

        match self.provider.generate(req).await {
            Ok(provider_result) => {
                result.prompt_tokens     = provider_result.prompt_tokens;
                result.completion_tokens = provider_result.completion_tokens;

                // ── Stage 5: Validate + retry ─────────────────────────────────
                let retry = RetryHandler::new(val_cfg.max_retries);
                let validation = retry
                    .validate_and_retry(
                        &provider_result,
                        &content,
                        Some(&self.schema),
                        self.provider.as_ref().as_ref(),
                        inf_cfg.temperature,
                        inf_cfg.max_tokens,
                    )
                    .await;

                result.is_valid          = validation.is_valid;
                result.structured_output = validation.data;
                result.validation_errors = validation.errors;
                result.latency_ms        = Some(call_start.elapsed().as_millis() as u64);

                if !result.is_valid {
                    warn!(
                        retries = val_cfg.max_retries,
                        "Validation failed after all retries"
                    );
                }
            }
            Err(e) => {
                warn!(error = %e, "LLM inference failed");
                result.validation_errors = vec![e.to_string()];
                result.latency_ms = Some(call_start.elapsed().as_millis() as u64);
            }
        }

        let elapsed = result.latency_ms.unwrap_or(0);
        spinner.finish_with_message(if result.is_valid {
            format!("✓  {format_label} structured in {elapsed}ms")
        } else {
            format!("✗  structuring failed for {format_label}")
        });

        info!(
            is_valid  = result.is_valid,
            elapsed_ms = start.elapsed().as_millis(),
            "Pipeline complete"
        );

        Ok(vec![result])
    }

    /// Process multiple files with a concurrency limit (one LLM call per file).
    pub async fn run_many(
        &self,
        file_paths: &[PathBuf],
        max_concurrent: usize,
        parser_override: Option<&str>,
        model: Option<&str>,
    ) -> Result<std::collections::HashMap<String, Vec<ExtractionResult>>> {
        let sem = Arc::new(Semaphore::new(max_concurrent));
        let mut handles = Vec::new();

        let pb = ProgressBar::new(file_paths.len() as u64);
        pb.set_style(
            ProgressStyle::with_template(
                "{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} files",
            )
            .unwrap()
            .progress_chars("#>-"),
        );

        for path in file_paths {
            let sem    = Arc::clone(&sem);
            let path   = path.clone();
            let schema = self.schema.clone();
            let task   = self.task.clone();
            let config = Arc::clone(&self.config);
            let parser_override = parser_override.map(|s| s.to_string());
            let model  = model.map(|s| s.to_string());
            let pb     = pb.clone();

            handles.push(tokio::spawn(async move {
                let _permit = sem.acquire().await.unwrap();

                let provider = match get_provider(&config.inference) {
                    Ok(p)  => p,
                    Err(e) => {
                        warn!(error = %e, "Failed to create provider");
                        pb.inc(1);
                        return (path.display().to_string(), Err(e));
                    }
                };

                let pipeline = Pipeline::with_provider(
                    schema,
                    &task,
                    (*config).clone(),
                    provider,
                );

                let result = pipeline
                    .run(&path, parser_override.as_deref(), model.as_deref())
                    .await;

                pb.inc(1);
                (path.display().to_string(), result)
            }));
        }

        let mut output = std::collections::HashMap::new();
        for handle in join_all(handles).await {
            if let Ok((name, result)) = handle {
                match result {
                    Ok(results) => { output.insert(name, results); }
                    Err(e)      => { warn!(file = name, error = %e, "File processing failed"); }
                }
            }
        }

        pb.finish_with_message("Batch complete");
        Ok(output)
    }
}

// ── Prompt builders ───────────────────────────────────────────────────────────

/// System prompt: tells the LLM its role and the exact JSON schema to follow.
fn build_system_prompt(schema: &Value) -> String {
    format!(
        "You are a precise data extraction assistant. \
         Read the entire document and extract ALL relevant structured information. \
         Return ONLY a valid JSON object matching this schema:\n\n\
         {schema}\n\n\
         Rules:\n\
         - Output only the JSON object — no markdown fences, no explanation\n\
         - Use null for fields not found in the document\n\
         - Capture every piece of data the document contains",
        schema = serde_json::to_string_pretty(schema).unwrap_or_default()
    )
}

/// User prompt: document type label + full preprocessed content.
fn build_extraction_prompt(format: &DocumentFormat, content: &str) -> String {
    format!(
        "[Document type: {format}]\n\n\
         --- BEGIN DOCUMENT ---\n\
         {content}\n\
         --- END DOCUMENT ---"
    )
}

// ── Context window management ─────────────────────────────────────────────────

/// Trim `text` so its estimated token count stays within `max_tokens`.
///
/// Uses a conservative 3 chars-per-token ratio (safer for non-ASCII text).
/// Truncation is aligned to the nearest whitespace boundary.
fn trim_to_context(text: &str, max_tokens: usize) -> String {
    let char_limit = max_tokens * 3;
    if text.len() <= char_limit {
        return text.to_string();
    }

    warn!(
        original_chars = text.len(),
        limit = char_limit,
        "Content exceeds estimated context window — truncating"
    );

    let truncated = &text[..char_limit];
    let safe_end  = truncated
        .rfind(|c: char| c.is_whitespace())
        .unwrap_or(char_limit);

    format!(
        "{}\n\n[... document truncated to fit the model context window ...]",
        truncated[..safe_end].trim_end()
    )
}
