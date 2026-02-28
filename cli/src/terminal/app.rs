use anyhow::Result;
use colored::Colorize;
use std::io::{self, Write};

const BANNER: &str = r#"
  _____ _                   _                    ____
 / ____| |                 | |                  |  _ \
| (___ | |_ _ __ _   _  ___| |_ _   _ _ __ ___ | | | |
 \___ \| __| '__| | | |/ __| __| | | | '__/ _ \| | | |
 ____) | |_| |  | |_| | (__| |_| |_| | | |  __/| |_| |
|_____/ \__|_|   \__,_|\___|\__|\__,_|_|  \___|_____/
"#;

const HELP_TEXT: &str = r#"
Commands:
  extract <file> [--schema <name>] [--model <model>]   Extract structured data
  batch <dir> [--concurrency <n>]                       Process a directory
  config                                                Show current config
  schemas                                               List built-in schemas
  help                                                  Show this help
  quit / exit / q                                       Exit

Provider shortcuts:
  :provider <name>    Switch provider (vllm|openai|anthropic|gemini|ollama)
  :schema <name>      Switch schema
  :model <name>       Set model override
"#;

/// Simple line-based interactive REPL (Phase 6 will upgrade to ratatui TUI).
pub fn run_interactive() -> Result<()> {
    println!("{}", BANNER.bright_cyan());
    println!("  {} {}", "Structure-D".bold(), "v0.1.0 — Interactive Mode".dimmed());
    println!("  Type {} for help, {} to quit.\n", "help".yellow(), "q".yellow());

    let stdin = io::stdin();
    let mut stdout = io::stdout();

    loop {
        print!("{} ", "structure-d>".bright_green().bold());
        stdout.flush()?;

        let mut line = String::new();
        if stdin.read_line(&mut line)? == 0 {
            // EOF
            break;
        }

        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        match line {
            "quit" | "exit" | "q" => {
                println!("{}", "Goodbye!".bright_cyan());
                break;
            }
            "help" | "?" => {
                println!("{}", HELP_TEXT);
            }
            "schemas" => {
                println!("\n{}", "Built-in schemas:".bold());
                for (name, desc) in crate::schemas::list_schemas() {
                    println!("  {:25} {}", name.yellow(), desc.dimmed());
                }
                println!();
            }
            "config" => {
                println!("{}", "  Use --config flag to specify a config file.".dimmed());
                println!("  Default: configs/default.yaml or ~/.structure-d/config.yaml\n");
            }
            other if other.starts_with("extract ") => {
                println!(
                    "{}",
                    "  Use the CLI: structure-d extract <file> [options]".dimmed()
                );
                println!("  Interactive extract coming in Phase 6 (ratatui TUI).\n");
            }
            _ => {
                println!("{} '{}'\n", "Unknown command:".red(), line);
            }
        }
    }

    Ok(())
}
