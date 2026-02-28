use anyhow::Result;
use clap::Args;
use colored::Colorize;

use crate::config::Settings;

#[derive(Args, Debug)]
pub struct ConfigArgs {
    /// Show sensitive values like API keys (masked by default)
    #[arg(long)]
    pub show_secrets: bool,
}

pub fn run(args: ConfigArgs, config: Settings) -> Result<()> {
    println!("\n{}\n", "Effective Configuration".bold().underline());

    // ── Inference ─────────────────────────────────────────────────────────
    println!("{}", "  Inference".bright_cyan().bold());
    println!("    provider       : {}", config.inference.provider.yellow());
    println!("    temperature    : {}", config.inference.temperature);
    println!("    max_tokens     : {}", config.inference.max_tokens);
    println!(
        "    batch size     : {}",
        config.inference.batch.max_batch_size
    );
    println!(
        "    concurrency    : {}",
        config.inference.batch.max_concurrent
    );

    match config.inference.provider.as_str() {
        "openai" => {
            println!("\n    {} settings:", "OpenAI".yellow());
            println!("      model        : {}", config.inference.openai.model);
            println!("      base_url     : {}", config.inference.openai.base_url);
            print_api_key(
                "      api_key      :",
                &config.inference.openai.api_key,
                "OPENAI_API_KEY",
                args.show_secrets,
            );
        }
        "anthropic" => {
            println!("\n    {} settings:", "Anthropic".yellow());
            println!("      model        : {}", config.inference.anthropic.model);
            print_api_key(
                "      api_key      :",
                &config.inference.anthropic.api_key,
                "ANTHROPIC_API_KEY",
                args.show_secrets,
            );
        }
        "gemini" => {
            println!("\n    {} settings:", "Gemini".yellow());
            println!("      model        : {}", config.inference.gemini.model);
            print_api_key(
                "      api_key      :",
                &config.inference.gemini.api_key,
                "GEMINI_API_KEY",
                args.show_secrets,
            );
        }
        "ollama" => {
            println!("\n    {} settings:", "Ollama".yellow());
            println!("      model        : {}", config.inference.ollama.model);
            println!("      base_url     : {}", config.inference.ollama.base_url);
        }
        _ => {
            println!("\n    {} settings:", "vLLM".yellow());
            println!("      model        : {}", config.inference.vllm.model);
            println!("      api_base     : {}", config.inference.vllm.api_base);
            println!(
                "      output_backend : {}",
                config.inference.vllm.structured_output_backend
            );
        }
    }

    // ── Preprocessing ─────────────────────────────────────────────────────
    println!("\n{}", "  Preprocessing".bright_cyan().bold());
    println!(
        "    chunking strategy : {}",
        config.preprocessing.chunking.strategy.yellow()
    );
    println!(
        "    max_tokens        : {}",
        config.preprocessing.chunking.max_tokens
    );
    println!(
        "    overlap           : {}",
        config.preprocessing.chunking.overlap
    );
    println!(
        "    normalize_unicode : {}",
        config.preprocessing.normalize_unicode
    );
    println!(
        "    strip_boilerplate : {}",
        config.preprocessing.strip_boilerplate
    );

    // ── Validation ────────────────────────────────────────────────────────
    println!("\n{}", "  Validation".bright_cyan().bold());
    println!("    max_retries    : {}", config.validation.max_retries);
    println!("    strict         : {}", config.validation.strict);
    println!(
        "    retry_prompt   : {}",
        config.validation.retry_with_refined_prompt
    );
    println!(
        "    regex_fallback : {}",
        config.validation.fallback_to_regex
    );

    // ── Storage ───────────────────────────────────────────────────────────
    println!("\n{}", "  Storage".bright_cyan().bold());
    println!(
        "    default_format : {}",
        config.storage.default_format.yellow()
    );
    println!("    output_dir     : {}", config.storage.output_dir);

    // ── API ───────────────────────────────────────────────────────────────
    println!("\n{}", "  API".bright_cyan().bold());
    println!(
        "    address        : {}:{}",
        config.api.host, config.api.port
    );

    // ── Monitoring ────────────────────────────────────────────────────────
    println!("\n{}", "  Monitoring".bright_cyan().bold());
    println!("    log_level      : {}", config.monitoring.log_level);
    println!(
        "    prometheus     : {}",
        if config.monitoring.prometheus_enabled {
            "enabled".green().to_string()
        } else {
            "disabled".dimmed().to_string()
        }
    );

    println!("\n  {} SD_<SECTION>__<KEY>=value", "Override via env:".dimmed());
    println!(
        "  {}  SD_INFERENCE__PROVIDER=openai\n",
        "   e.g.".dimmed()
    );

    Ok(())
}

fn print_api_key(label: &str, key: &Option<String>, env_var: &str, show: bool) {
    let env_val = std::env::var(env_var).ok();
    let effective = key.as_deref().or(env_val.as_deref());

    match effective {
        Some(k) if show => println!("{} {}", label, k.yellow()),
        Some(k) => {
            let masked = format!("{}...{}", &k[..4.min(k.len())], &k[k.len().saturating_sub(4)..]);
            println!("{} {} (use --show-secrets to reveal)", label, masked.yellow());
        }
        None => println!(
            "{} {} (set via {} env var)",
            label,
            "not set".red(),
            env_var
        ),
    }
}
