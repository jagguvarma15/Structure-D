mod cli;
mod config;
mod errors;
mod inference;
mod ingestion;
mod pipeline;
mod preprocessing;
mod schemas;
mod storage;
mod terminal;
mod validation;

use anyhow::Result;
use clap::Parser;
use colored::Colorize;
use tracing_subscriber::{fmt, prelude::*, EnvFilter};

use cli::{Cli, Commands};
use config::Settings;

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialise structured logging
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&cli.log_level));

    tracing_subscriber::registry()
        .with(fmt::layer().with_target(false).compact())
        .with(env_filter)
        .init();

    // Load configuration (info commands don't need it, but config errors should surface early)
    let config = match Settings::load(cli.config.as_ref()) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("{} {}", "Config error:".red().bold(), e);
            std::process::exit(1);
        }
    };

    match cli.command {
        // Default: launch interactive terminal
        None | Some(Commands::Interactive) => {
            terminal::run_interactive()?;
        }

        // ── Core pipeline commands ─────────────────────────────────────────
        Some(Commands::Extract(args)) => {
            cli::commands::extract::run(args, config).await?;
        }

        Some(Commands::Batch(args)) => {
            cli::commands::batch::run(args, config).await?;
        }

        // ── Inspection / discovery commands ───────────────────────────────
        Some(Commands::Config(args)) => {
            cli::commands::config::run(args, config)?;
        }

        Some(Commands::Providers(args)) => {
            cli::commands::providers::run(args, config).await?;
        }

        Some(Commands::Models(args)) => {
            cli::commands::models::run(args, config)?;
        }

        Some(Commands::Schemas(args)) => {
            cli::commands::schemas::run(args)?;
        }

        Some(Commands::Formats) => {
            cli::commands::formats::run()?;
        }
    }

    Ok(())
}
