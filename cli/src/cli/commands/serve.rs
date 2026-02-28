use anyhow::Result;
use clap::Args;
use colored::Colorize;

use crate::config::Settings;

#[derive(Args, Debug)]
pub struct ServeArgs {
    /// Host to bind to
    #[arg(long, default_value = "0.0.0.0")]
    pub host: String,

    /// Port to listen on
    #[arg(short, long, default_value = "7433")]
    pub port: u16,
}

pub async fn run(args: ServeArgs, _config: Settings) -> Result<()> {
    println!(
        "{} Built-in REST server is planned for a future release.",
        "Note:".yellow().bold()
    );
    println!(
        "  Use the Python FastAPI server for now:\n  {}",
        "uvicorn structure_d.api.app:create_app --factory --host {} --port {}"
            .dimmed()
            .replace("{}", &args.host)
    );
    Ok(())
}
