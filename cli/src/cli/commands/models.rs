use anyhow::Result;
use clap::Args;
use colored::Colorize;
use std::path::{Path, PathBuf};

use crate::config::Settings;

#[derive(Args, Debug)]
pub struct ModelsArgs {
    /// Show full model details including description
    #[arg(short, long)]
    pub verbose: bool,
}

pub fn run(args: ModelsArgs, config: Settings) -> Result<()> {
    println!("\n{}", "Available Models".bold().underline());
    println!(
        "  Active provider: {}\n",
        config.inference.provider.bright_cyan()
    );

    // Search paths for models.yaml (with proper ~ expansion)
    let mut search_paths: Vec<PathBuf> = vec![
        PathBuf::from("configs/models.yaml"),
        PathBuf::from("models.yaml"),
    ];
    if let Some(home) = dirs::home_dir() {
        search_paths.push(home.join(".structure-d").join("models.yaml"));
    }

    let mut loaded = false;
    for path in &search_paths {
        if path.exists() {
            match load_models_yaml(path, args.verbose) {
                Ok(_) => {
                    loaded = true;
                    break;
                }
                Err(e) => {
                    eprintln!("  Warning: failed to load {}: {}", path.display(), e);
                }
            }
        }
    }

    if !loaded {
        println!(
            "  {}\n",
            "No models.yaml found. Showing provider defaults from config:".dimmed()
        );

        println!(
            "  {:<12} {:<45} {}",
            "Provider".bold(),
            "Model".bold(),
            "Endpoint".bold()
        );
        println!("  {}", "-".repeat(80));

        println!(
            "  {:<12} {:<45} {}",
            "vllm".yellow(),
            config.inference.vllm.model,
            config.inference.vllm.api_base.dimmed()
        );
        println!(
            "  {:<12} {:<45} {}",
            "openai".yellow(),
            config.inference.openai.model,
            config.inference.openai.base_url.dimmed()
        );
        println!(
            "  {:<12} {:<45} {}",
            "anthropic".yellow(),
            config.inference.anthropic.model,
            "https://api.anthropic.com/v1".dimmed()
        );
        println!(
            "  {:<12} {:<45} {}",
            "gemini".yellow(),
            config.inference.gemini.model,
            "https://generativelanguage.googleapis.com/v1beta".dimmed()
        );
        println!(
            "  {:<12} {:<45} {}",
            "ollama".yellow(),
            config.inference.ollama.model,
            config.inference.ollama.base_url.dimmed()
        );

        println!("\n  {} configs/models.yaml", "Add a model registry:".dimmed());
    }

    println!();
    Ok(())
}

fn load_models_yaml(path: &Path, verbose: bool) -> Result<()> {
    let content = std::fs::read_to_string(path)?;
    let yaml: serde_yaml::Value = serde_yaml::from_str(&content)?;

    println!("  {} {}\n", "Registry:".dimmed(), path.display());

    let models = yaml
        .get("models")
        .and_then(|m| m.as_sequence())
        .map(|s| s.as_slice())
        .unwrap_or(&[]);

    if models.is_empty() {
        println!("  {}", "No models found in registry.".dimmed());
        return Ok(());
    }

    println!(
        "  {:<22} {:<35} {:<12} {}",
        "Name".bold(),
        "Model ID".bold(),
        "Provider".bold(),
        "Tasks".bold()
    );
    println!("  {}", "-".repeat(90));

    for model in models {
        let name = model.get("name").and_then(|v| v.as_str()).unwrap_or("?");
        let model_id = model
            .get("model_id")
            .or_else(|| model.get("id"))
            .and_then(|v| v.as_str())
            .unwrap_or(name); // fall back to name if no model_id key
        let provider = model
            .get("provider")
            .and_then(|v| v.as_str())
            .unwrap_or("?");
        let tasks = model
            .get("tasks")
            .and_then(|v| v.as_sequence())
            .map(|seq| {
                seq.iter()
                    .filter_map(|t| t.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            })
            .unwrap_or_default();

        println!(
            "  {:<22} {:<35} {:<12} {}",
            name.yellow(),
            model_id,
            provider.cyan(),
            tasks.dimmed()
        );

        if verbose {
            if let Some(desc) = model.get("description").and_then(|v| v.as_str()) {
                println!("    {}", desc.dimmed());
            }
            if let Some(ctx) = model.get("context_length").and_then(|v| v.as_u64()) {
                println!("    context: {} tokens", ctx);
            }
        }
    }

    Ok(())
}
