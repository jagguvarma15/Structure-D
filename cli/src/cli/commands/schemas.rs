use anyhow::Result;
use clap::Args;
use colored::Colorize;

use crate::schemas::{list_schemas, resolve_schema};

#[derive(Args, Debug)]
pub struct SchemasArgs {
    /// Print the full JSON Schema definition for a specific schema
    #[arg(value_name = "NAME")]
    pub name: Option<String>,
}

pub fn run(args: SchemasArgs) -> Result<()> {
    if let Some(name) = args.name {
        // Print full schema definition
        let schema = resolve_schema(&name)?;
        println!("{}", serde_json::to_string_pretty(&schema)?);
    } else {
        // List all schemas
        println!("\n{}\n", "Built-in Schemas".bold().underline());
        for (name, desc) in list_schemas() {
            println!("  {:<30} {}", name.yellow(), desc.dimmed());
        }
        println!();
        println!(
            "  {}  structure-d extract file.pdf {}",
            "Usage:".bold(),
            "--schema key_value".yellow()
        );
        println!(
            "  {}  structure-d schemas {}",
            "Inspect:".bold(),
            "key_value".yellow()
        );
        println!(
            "  {}  Pass a .json file path to use a custom schema.\n",
            "Custom:".bold()
        );
    }
    Ok(())
}
