use anyhow::Result;
use clap::Args;
use colored::Colorize;
use std::path::PathBuf;

use crate::config::Settings;
use crate::pipeline::Pipeline;
use crate::schemas::resolve_schema;
use crate::storage::{jsonl, csv_store};

#[derive(Args, Debug)]
pub struct BatchArgs {
    /// Directory containing files to process
    #[arg(required = true, value_name = "DIR")]
    pub directory: PathBuf,

    /// Max parallel files (default: from config)
    #[arg(short, long, default_value = "4", value_name = "N")]
    pub concurrency: usize,

    /// Recurse into subdirectories
    #[arg(short, long)]
    pub recursive: bool,

    /// Task type: extraction, classification, summarisation, sentiment
    #[arg(short, long, default_value = "extraction")]
    pub task: String,

    /// Schema: built-in name or path to JSON schema file
    #[arg(short, long, default_value = "generic")]
    pub schema: String,

    /// Output format: jsonl or csv
    #[arg(short = 'f', long, default_value = "jsonl",
          value_parser = clap::builder::PossibleValuesParser::new(["jsonl", "csv"]))]
    pub output_format: String,

    /// Output file path
    #[arg(short, long, value_name = "FILE")]
    pub output: Option<PathBuf>,

    /// File extensions to include (e.g., pdf,txt,html). Default: all supported.
    #[arg(long, value_delimiter = ',')]
    pub extensions: Vec<String>,
}

pub async fn run(args: BatchArgs, config: Settings) -> Result<()> {
    if !args.directory.is_dir() {
        anyhow::bail!("'{}' is not a directory", args.directory.display());
    }

    // Collect files
    let supported_exts = if args.extensions.is_empty() {
        vec!["pdf", "html", "htm", "xlsx", "xls", "eml", "txt", "md", "csv"]
            .into_iter()
            .map(|s| s.to_string())
            .collect::<Vec<_>>()
    } else {
        args.extensions.clone()
    };

    let files = collect_files(&args.directory, args.recursive, &supported_exts)?;

    if files.is_empty() {
        println!("{}", "No supported files found in directory.".yellow());
        return Ok(());
    }

    println!(
        "{} {} files in {}",
        "Found".bright_blue().bold(),
        files.len(),
        args.directory.display()
    );

    let schema = resolve_schema(&args.schema)?;
    let pipeline = Pipeline::new(schema, &args.task, config)?;

    let results_map = pipeline
        .run_many(&files, args.concurrency, None, None)
        .await?;

    let all_results: Vec<_> = results_map.into_values().flatten().collect();

    println!(
        "{} {} total results from {} files",
        "Extracted".bright_green().bold(),
        all_results.len(),
        files.len()
    );

    // Store output
    match args.output_format.as_str() {
        "jsonl" => {
            let path = args
                .output
                .unwrap_or_else(|| PathBuf::from("output/batch_results.jsonl"));
            jsonl::save_as_jsonl(&all_results, &path.display().to_string())?;
            println!("{} → {}", "Saved".bright_green(), path.display());
        }
        "csv" => {
            let path = args
                .output
                .unwrap_or_else(|| PathBuf::from("output/batch_results.csv"));
            csv_store::save_as_csv(&all_results, &path.display().to_string())?;
            println!("{} → {}", "Saved".bright_green(), path.display());
        }
        _ => unreachable!(),
    }

    Ok(())
}

fn collect_files(dir: &PathBuf, recursive: bool, extensions: &[String]) -> Result<Vec<PathBuf>> {
    let mut files = Vec::new();

    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();

        if path.is_dir() && recursive {
            files.extend(collect_files(&path, recursive, extensions)?);
        } else if path.is_file() {
            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();
            if extensions.iter().any(|e| e == &ext) {
                files.push(path);
            }
        }
    }

    Ok(files)
}
