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

    // Initialise tracing / structured logging
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&cli.log_level));

    tracing_subscriber::registry()
        .with(fmt::layer().with_target(false).compact())
        .with(env_filter)
        .init();

    // Load configuration
    let config = match Settings::load(cli.config.as_ref()) {
        Ok(cfg) => cfg,
        Err(e) => {
            eprintln!("{} {}", "Config error:".red().bold(), e);
            std::process::exit(1);
        }
    };

    // Dispatch to subcommand (or interactive if none given)
    match cli.command {
        None | Some(Commands::Interactive) => {
            terminal::run_interactive()?;
        }

        Some(Commands::Extract(args)) => {
            cli::commands::extract::run(args, config).await?;
        }

        Some(Commands::Batch(args)) => {
            cli::commands::batch::run(args, config).await?;
        }

        Some(Commands::Serve(args)) => {
            cli::commands::serve::run(args, config).await?;
        }

        Some(Commands::Models(args)) => {
            cli::commands::models::run(args, config)?;
        }

        Some(Commands::Schemas) => {
            println!("\n{}", "Built-in Schemas".bold().underline());
            println!();
            for (name, desc) in schemas::list_schemas() {
                println!("  {:<30} {}", name.yellow(), desc.dimmed());
            }
            println!();
            println!(
                "  {} structure-d extract file.pdf --schema <name>",
                "Usage:".bold()
            );
            println!(
                "  {} Pass a JSON file path to use a custom schema.\n",
                "       ".dimmed()
            );
        }

        Some(Commands::Formats) => {
            println!("\n{}", "Supported File Formats".bold().underline());
            println!();
            for (fmt_name, desc) in ingestion::SUPPORTED_FORMATS {
                println!("  {:<20} {}", fmt_name.yellow(), desc.dimmed());
            }
            println!();
        }
    }

    Ok(())
}
