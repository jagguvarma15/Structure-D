use anyhow::Result;
use clap::Args;
use colored::Colorize;

use crate::config::Settings;

#[derive(Args, Debug)]
pub struct ProvidersArgs {
    /// Test connectivity to the active provider (makes a minimal request)
    #[arg(long)]
    pub check: bool,
}

pub async fn run(args: ProvidersArgs, config: Settings) -> Result<()> {
    println!("\n{}\n", "Configured Providers".bold().underline());

    let active = &config.inference.provider;

    let providers = [
        ProviderInfo {
            name: "vllm",
            model: &config.inference.vllm.model,
            endpoint: &config.inference.vllm.api_base,
            api_key_source: None,
            key_env: None,
        },
        ProviderInfo {
            name: "openai",
            model: &config.inference.openai.model,
            endpoint: &config.inference.openai.base_url,
            api_key_source: config.inference.openai.api_key.as_deref(),
            key_env: Some("OPENAI_API_KEY"),
        },
        ProviderInfo {
            name: "anthropic",
            model: &config.inference.anthropic.model,
            endpoint: "https://api.anthropic.com/v1",
            api_key_source: config.inference.anthropic.api_key.as_deref(),
            key_env: Some("ANTHROPIC_API_KEY"),
        },
        ProviderInfo {
            name: "gemini",
            model: &config.inference.gemini.model,
            endpoint: "https://generativelanguage.googleapis.com/v1beta",
            api_key_source: config.inference.gemini.api_key.as_deref(),
            key_env: Some("GEMINI_API_KEY"),
        },
        ProviderInfo {
            name: "ollama",
            model: &config.inference.ollama.model,
            endpoint: &config.inference.ollama.base_url,
            api_key_source: None,
            key_env: None,
        },
    ];

    for p in &providers {
        let is_active = p.name == active;
        let marker = if is_active {
            "▶".bright_green().bold().to_string()
        } else {
            " ".to_string()
        };

        let key_status = key_status(p.api_key_source, p.key_env);
        let name_str = if is_active {
            p.name.bright_green().bold().to_string()
        } else {
            p.name.normal().to_string()
        };

        println!(
            "{} {:<12}  model: {:<45}  key: {}",
            marker, name_str, p.model, key_status
        );
        println!("             endpoint: {}", p.endpoint.dimmed());
        println!();
    }

    // ── Connectivity check ────────────────────────────────────────────────
    if args.check {
        println!("{}", "Connectivity check:".bold());
        check_active_provider(&config).await;
    } else {
        println!(
            "  {} structure-d providers --check",
            "Test connectivity:".dimmed()
        );
        println!(
            "  {} SD_INFERENCE__PROVIDER=openai structure-d providers",
            "Switch provider:".dimmed()
        );
    }

    println!();
    Ok(())
}

struct ProviderInfo<'a> {
    name: &'a str,
    model: &'a str,
    endpoint: &'a str,
    api_key_source: Option<&'a str>,
    key_env: Option<&'a str>,
}

fn key_status(config_key: Option<&str>, env_var: Option<&str>) -> String {
    let env_val = env_var.and_then(|e| std::env::var(e).ok());
    let effective = config_key.or(env_val.as_deref());

    match effective {
        Some(k) if !k.is_empty() => {
            let masked = if k.len() > 8 {
                format!("{}...{}", &k[..4], &k[k.len() - 4..])
            } else {
                "****".to_string()
            };
            format!("{} ({})", "set".bright_green(), masked.dimmed())
        }
        _ => match env_var {
            None => "no key needed".dimmed().to_string(),
            Some(env) => format!("{} (set {})", "not set".red(), env),
        },
    }
}

async fn check_active_provider(config: &Settings) {
    use crate::inference::get_provider;

    print!("  Connecting to {} ... ", config.inference.provider.yellow());

    let provider = match get_provider(&config.inference) {
        Ok(p) => p,
        Err(e) => {
            println!("{} {}", "✗".bright_red(), e);
            return;
        }
    };

    // Send a minimal prompt (no schema, minimal tokens) to check reachability
    let req = crate::inference::GenerateRequest::new("Say 'ok'.")
        .with_max_tokens(5)
        .with_temperature(0.0);

    match provider.generate(req).await {
        Ok(r) => println!(
            "{} (model: {}, tokens used: {})",
            "✓ reachable".bright_green(),
            r.model.dimmed(),
            r.completion_tokens.unwrap_or(0)
        ),
        Err(e) => println!("{} {}", "✗".bright_red(), e),
    }
}
