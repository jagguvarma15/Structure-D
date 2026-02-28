use anyhow::Result;
use clap::Args;
use colored::Colorize;
use std::path::Path;

use crate::config::Settings;

#[derive(Args, Debug)]
pub struct ModelsArgs {
    /// Show full model details
    #[arg(short, long)]
    pub verbose: bool,
}

pub fn run(args: ModelsArgs, config: Settings) -> Result<()> {
    println!("\n{}", "Available Models".bold().underline());
    println!(
        "  Active provider: {}\n",
        config.inference.provider.bright_cyan()
    );

    // Try to load models.yaml from standard locations
    // Check for models.yaml
    let yaml_paths = [
        "configs/models.yaml",
        "models.yaml",
        "~/.structure-d/models.yaml",
    ];

    let mut loaded = false;
    for yaml_path in &yaml_paths {
        let path = Path::new(yaml_path);
        if path.exists() {
            match load_models_yaml(path, args.verbose) {
                Ok(_) => {
                    loaded = true;
                    break;
                }
                Err(e) => {
                    eprintln!("  Warning: failed to load {}: {}", yaml_path, e);
                }
            }
        }
    }

    if !loaded {
        // Show provider defaults from config
        println!("  {}", "No models.yaml found. Showing config defaults:".dimmed());
        println!();

        let rows = vec![
            ("vllm", &config.inference.vllm.model, &config.inference.vllm.api_base),
            ("openai", &config.inference.openai.model, &config.inference.openai.base_url),
            ("ollama", &config.inference.ollama.model, &config.inference.ollama.base_url),
        ];

        println!(
            "  {:<12} {:<40} {}",
            "Provider".bold(),
            "Default Model".bold(),
            "API Base".bold()
        );
        println!("  {}", "-".repeat(80));
        for (provider, model, base) in rows {
            println!(
                "  {:<12} {:<40} {}",
                provider.yellow(),
                model,
                base.dimmed()
            );
        }
        println!();
        println!("  {}", "Anthropic:".yellow());
        println!("    Model: {}", config.inference.anthropic.model);
        println!();
        println!("  {}", "Gemini:".yellow());
        println!("    Model: {}", config.inference.gemini.model);
    }

    println!();
    Ok(())
}

fn load_models_yaml(path: &Path, verbose: bool) -> Result<()> {
    let content = std::fs::read_to_string(path)?;
    let yaml: serde_yaml::Value = serde_yaml::from_str(&content)?;

    println!("  {} {}\n", "Registry:".dimmed(), path.display());

    if let Some(models) = yaml.get("models").and_then(|m| m.as_sequence()) {
        println!(
            "  {:<20} {:<30} {:<15} {}",
            "Name".bold(),
            "Model ID".bold(),
            "Provider".bold(),
            "Tasks".bold()
        );
        println!("  {}", "-".repeat(80));

        for model in models {
            let name = model.get("name").and_then(|v| v.as_str()).unwrap_or("?");
            let model_id = model.get("model_id").and_then(|v| v.as_str()).unwrap_or("?");
            let provider = model.get("provider").and_then(|v| v.as_str()).unwrap_or("?");
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
                "  {:<20} {:<30} {:<15} {}",
                name.yellow(),
                model_id,
                provider.cyan(),
                tasks.dimmed()
            );

            if verbose {
                if let Some(desc) = model.get("description").and_then(|v| v.as_str()) {
                    println!("    {}", desc.dimmed());
                }
            }
        }
    } else {
        println!("  {}", "No models found in registry.".dimmed());
    }

    Ok(())
}
