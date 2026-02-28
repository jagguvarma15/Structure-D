use anyhow::Result;
use colored::Colorize;

use crate::ingestion::SUPPORTED_FORMATS;

pub fn run() -> Result<()> {
    println!("\n{}\n", "Supported File Formats".bold().underline());
    for (fmt_name, desc) in SUPPORTED_FORMATS {
        println!("  {:<22} {}", fmt_name.yellow(), desc.dimmed());
    }
    println!();
    println!(
        "  {}  structure-d extract file.pdf {}",
        "Usage:".bold(),
        "--schema key_value".yellow()
    );
    println!(
        "  {}  Use {} to override auto-detection.\n",
        "Parser:".bold(),
        "--parser pdf".yellow()
    );
    Ok(())
}
