use anyhow::Result;
use clap::Args;
use colored::Colorize;
use std::path::PathBuf;

use crate::config::Settings;
use crate::pipeline::Pipeline;
use crate::schemas::resolve_schema;
use crate::storage::{csv_store, jsonl, markdown, ExtractionResult};

#[derive(Args, Debug)]
pub struct ExtractArgs {
    /// One or more input files
    #[arg(required = true, value_name = "FILES")]
    pub files: Vec<PathBuf>,

    /// Task type: extraction, classification, summarisation, sentiment
    #[arg(short, long, default_value = "extraction", value_name = "TASK")]
    pub task: String,

    /// Model name or alias (default: from config)
    #[arg(short, long, value_name = "MODEL")]
    pub model: Option<String>,

    /// Parser override (pdf, html, xlsx, eml, txt)
    #[arg(short, long, value_name = "PARSER")]
    pub parser: Option<String>,

    /// Schema: built-in name or path to JSON schema file
    #[arg(short, long, default_value = "generic", value_name = "SCHEMA")]
    pub schema: String,

    /// Output format: jsonl, csv, or md
    #[arg(short = 'f', long, default_value = "jsonl", value_name = "FORMAT",
          value_parser = clap::builder::PossibleValuesParser::new(["jsonl", "csv", "md"]))]
    pub output_format: String,

    /// Output file path (default: stdout for jsonl, ./output/results.csv|md for others)
    #[arg(short, long, value_name = "FILE")]
    pub output: Option<PathBuf>,

    /// Override LLM provider for this run
    #[arg(long, value_name = "PROVIDER")]
    pub provider: Option<String>,
}

pub async fn run(args: ExtractArgs, mut config: Settings) -> Result<()> {
    // Override provider if specified
    if let Some(provider) = &args.provider {
        config.inference.provider = provider.clone();
    }

    // Resolve schema
    let schema = resolve_schema(&args.schema)?;

    // Build pipeline
    let pipeline = Pipeline::new(schema, &args.task, config)?;

    let mut all_results: Vec<ExtractionResult> = Vec::new();

    for file_path in &args.files {
        println!(
            "{} {}",
            "Processing:".bright_blue().bold(),
            file_path.display()
        );

        match pipeline
            .run(file_path, args.parser.as_deref(), args.model.as_deref())
            .await
        {
            Ok(results) => {
                let valid = results.iter().filter(|r| r.is_valid).count();
                println!(
                    "  {} {}/{} chunks valid",
                    "✓".bright_green(),
                    valid,
                    results.len()
                );
                all_results.extend(results);
            }
            Err(e) => {
                eprintln!("  {} {}: {}", "✗".bright_red(), file_path.display(), e);
            }
        }
    }

    if all_results.is_empty() {
        eprintln!("{}", "No results extracted.".yellow());
        return Ok(());
    }

    // ── Stage 6: Store ────────────────────────────────────────────────────
    match args.output_format.as_str() {
        "jsonl" => {
            if let Some(output_path) = &args.output {
                jsonl::save_as_jsonl(&all_results, &output_path.display().to_string())?;
                println!(
                    "{} {} results → {}",
                    "Saved".bright_green().bold(),
                    all_results.len(),
                    output_path.display()
                );
            } else {
                // Print to stdout
                jsonl::print_as_jsonl(&all_results)?;
            }
        }
        "csv" => {
            let output_path = args
                .output
                .clone()
                .unwrap_or_else(|| PathBuf::from("output/results.csv"));
            csv_store::save_as_csv(&all_results, &output_path.display().to_string())?;
            println!(
                "{} {} results → {}",
                "Saved".bright_green().bold(),
                all_results.len(),
                output_path.display()
            );
        }
        "md" => {
            let output_path = args
                .output
                .clone()
                .unwrap_or_else(|| PathBuf::from("output/results.md"));
            markdown::save_as_markdown(&all_results, &output_path.display().to_string())?;
            println!(
                "{} {} results → {}",
                "Saved".bright_green().bold(),
                all_results.len(),
                output_path.display()
            );
        }
        _ => unreachable!(),
    }

    Ok(())
}
