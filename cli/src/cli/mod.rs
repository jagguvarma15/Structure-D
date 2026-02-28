pub mod commands;

use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(
    name = "structure-d",
    version = env!("CARGO_PKG_VERSION"),
    author,
    about = "Convert unstructured documents to validated structured data",
    long_about = None,
)]
pub struct Cli {
    /// Path to config file (default: configs/default.yaml)
    #[arg(short, long, global = true, value_name = "FILE")]
    pub config: Option<PathBuf>,

    /// Log level: error, warn, info, debug, trace
    #[arg(short, long, global = true, default_value = "warn", env = "SD_LOG_LEVEL")]
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

    /// Start the built-in REST API server (coming soon)
    Serve(commands::serve::ServeArgs),

    /// List available models from the model registry
    Models(commands::models::ModelsArgs),

    /// List built-in extraction schemas
    Schemas,

    /// List supported file formats and their parsers
    Formats,

    /// Launch interactive terminal (default when no command given)
    Interactive,
}
