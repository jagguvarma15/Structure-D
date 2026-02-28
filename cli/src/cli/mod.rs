pub mod commands;

use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "structure-d",
    version = env!("CARGO_PKG_VERSION"),
    author,
    about = "Convert unstructured documents to validated structured data",
    long_about = "Structure-D: Ingest unstructured files (PDF, HTML, XLSX, email, text)\n\
                  and extract validated structured data via any LLM provider.",
)]
pub struct Cli {
    /// Path to config file (overrides configs/default-rust.yaml)
    #[arg(long, global = true, value_name = "FILE")]
    pub config: Option<PathBuf>,

    /// Log level: error, warn, info, debug, trace
    #[arg(short = 'L', long, global = true, default_value = "warn", env = "SD_LOG_LEVEL")]
    pub log_level: String,

    #[command(subcommand)]
    pub command: Option<Commands>,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    /// Extract structured data from one or more files
    Extract(commands::extract::ExtractArgs),

    /// Process all files in a directory concurrently
    Batch(commands::batch::BatchArgs),

    /// Show effective configuration (resolved from file + env vars)
    Config(commands::config::ConfigArgs),

    /// List and check configured LLM providers
    Providers(commands::providers::ProvidersArgs),

    /// List available models from the model registry
    Models(commands::models::ModelsArgs),

    /// List built-in schemas (or print a schema definition)
    Schemas(commands::schemas::SchemasArgs),

    /// List supported file formats and parsers
    Formats,

    /// Launch the interactive terminal
    Interactive,
}
