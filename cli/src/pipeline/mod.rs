use anyhow::Result;
use futures::future::join_all;
use indicatif::{ProgressBar, ProgressStyle};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::Semaphore;
use tracing::{debug, info, warn};

use crate::config::Settings;
use crate::ingestion::{parse_file, ParsedDocument};
use crate::inference::{get_provider, GenerateRequest, LLMProvider};
use crate::preprocessing::{normalize_text, Chunker};
use crate::storage::ExtractionResult;
use crate::validation::{retry::RetryHandler, validate};

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

    /// With a pre-built provider (for testing / custom providers).
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

    /// Process a single file through the 6-stage pipeline.
    pub async fn run(
        &self,
        file_path: &Path,
        parser_override: Option<&str>,
        model: Option<&str>,
    ) -> Result<Vec<ExtractionResult>> {
        let start = Instant::now();

        // ── Stage 1: Ingest ───────────────────────────────────────────────
        debug!(path = %file_path.display(), "Ingesting file");
        let doc = parse_file(file_path, parser_override)?;
        info!(
            path = %file_path.display(),
            format = %doc.format,
            chars = doc.content.len(),
            "Ingestion complete"
        );

        self.run_on_document(doc, model, start).await
    }

    /// Process a ParsedDocument (useful when ingestion is done externally).
    async fn run_on_document(
        &self,
        doc: ParsedDocument,
        model: Option<&str>,
        start: Instant,
    ) -> Result<Vec<ExtractionResult>> {
        let pre_cfg = &self.config.preprocessing;
        let inf_cfg = &self.config.inference;
        let val_cfg = &self.config.validation;

        // ── Stage 2: Preprocess ───────────────────────────────────────────
        let normalized = normalize_text(
            &doc.content,
            pre_cfg.normalize_unicode,
            pre_cfg.strip_boilerplate,
            pre_cfg.collapse_whitespace,
        );

        let chunker = Chunker::new(
            &pre_cfg.chunking.strategy,
            pre_cfg.chunking.max_tokens,
            pre_cfg.chunking.overlap,
        );
        let chunks = chunker.chunk(&normalized, doc.id);
        info!(chunks = chunks.len(), "Text chunked");

        // ── Stage 3: Route (model selection) ─────────────────────────────
        let model_name = model
            .map(|s| s.to_string())
            .unwrap_or_else(|| match inf_cfg.provider.as_str() {
                "openai" => inf_cfg.openai.model.clone(),
                "anthropic" => inf_cfg.anthropic.model.clone(),
                "gemini" => inf_cfg.gemini.model.clone(),
                "ollama" => inf_cfg.ollama.model.clone(),
                _ => inf_cfg.vllm.model.clone(),
            });

        // ── Stages 4+5: Infer + Validate (concurrent per chunk) ───────────
        let _retry_handler = RetryHandler::new(val_cfg.max_retries);
        let sem = Arc::new(Semaphore::new(inf_cfg.batch.max_concurrent));
        let provider = Arc::clone(&self.provider);
        let schema = self.schema.clone();
        let task = self.task.clone();
        let source_path = doc.source_path.clone();
        let format_str = doc.format.to_string();
        let temperature = inf_cfg.temperature;
        let max_tokens_infer = inf_cfg.max_tokens;
        let _max_retries = val_cfg.max_retries;

        let pb = ProgressBar::new(chunks.len() as u64);
        pb.set_style(
            ProgressStyle::with_template(
                "{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] {pos}/{len} chunks",
            )
            .unwrap()
            .progress_chars("#>-"),
        );

        let handles: Vec<_> = chunks
            .into_iter()
            .map(|chunk| {
                let sem = Arc::clone(&sem);
                let provider = Arc::clone(&provider);
                let schema = schema.clone();
                let task = task.clone();
                let source_path = source_path.clone();
                let format_str = format_str.clone();
                let model_name = model_name.clone();
                let doc_id = doc.id;
                let pb = pb.clone();

                tokio::spawn(async move {
                    let _permit = sem.acquire().await.unwrap();
                    let chunk_start = Instant::now();

                    let prompt = format!(
                        "Extract structured information from the following text:\n\n{}",
                        chunk.text
                    );

                    let req = GenerateRequest::new(&prompt)
                        .with_schema(&schema)
                        .with_temperature(temperature)
                        .with_max_tokens(max_tokens_infer)
                        .with_model(&model_name);

                    let mut result = ExtractionResult::new(
                        doc_id,
                        chunk.chunk_index,
                        source_path.clone(),
                        format_str.clone(),
                        task.clone(),
                    );
                    result.model_used = Some(model_name.clone());

                    match provider.generate(req).await {
                        Ok(provider_result) => {
                            result.prompt_tokens = provider_result.prompt_tokens;
                            result.completion_tokens = provider_result.completion_tokens;
                            result.latency_ms =
                                Some(chunk_start.elapsed().as_millis() as u64);

                            // Stage 5: Validate
                            let validation = validate(&provider_result.content);
                            result.is_valid = validation.is_valid;
                            result.structured_output = validation.data;
                            result.validation_errors = validation.errors;

                            // If invalid, retry (without async retry for now — sync validation)
                            if !result.is_valid {
                                warn!(
                                    chunk = chunk.chunk_index,
                                    "Validation failed, result marked invalid"
                                );
                            }
                        }
                        Err(e) => {
                            warn!(chunk = chunk.chunk_index, error = %e, "Inference failed");
                            result.validation_errors = vec![e.to_string()];
                        }
                    }

                    pb.inc(1);
                    result
                })
            })
            .collect();

        let results_raw: Vec<ExtractionResult> = join_all(handles)
            .await
            .into_iter()
            .filter_map(|r| r.ok())
            .collect();

        pb.finish_with_message("Done");

        let elapsed = start.elapsed();
        info!(
            results = results_raw.len(),
            elapsed_ms = elapsed.as_millis(),
            "Pipeline complete"
        );

        Ok(results_raw)
    }

    /// Process multiple files concurrently with a semaphore.
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
            let sem = Arc::clone(&sem);
            let path = path.clone();
            let schema = self.schema.clone();
            let task = self.task.clone();
            let config = Arc::clone(&self.config);
            let _provider_name = self.config.inference.provider.clone();
            let parser_override = parser_override.map(|s| s.to_string());
            let model = model.map(|s| s.to_string());
            let pb = pb.clone();

            handles.push(tokio::spawn(async move {
                let _permit = sem.acquire().await.unwrap();

                let provider = match get_provider(&config.inference) {
                    Ok(p) => p,
                    Err(e) => {
                        warn!(error = %e, "Failed to create provider for batch task");
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

        pb.finish_with_message("Batch complete");

        let mut output = std::collections::HashMap::new();
        for handle in join_all(handles).await {
            if let Ok((name, result)) = handle {
                match result {
                    Ok(results) => { output.insert(name, results); }
                    Err(e) => { warn!(file = name, error = %e, "File processing failed"); }
                }
            }
        }

        Ok(output)
    }
}
