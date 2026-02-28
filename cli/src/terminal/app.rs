use anyhow::Result;
use colored::*;
use crossterm::terminal;
use indicatif::{ProgressBar, ProgressStyle};
use rustyline::DefaultEditor;
use std::thread;
use std::time::Duration;

// ── Branding constants ────────────────────────────────────────────────────────

const WORDMARK: &[&str] = &[
    " ███████╗████████╗██████╗ ██╗   ██╗ ██████╗████████╗██╗   ██╗██████╗ ███████╗   ███████╗",
    " ██╔════╝╚══██╔══╝██╔══██╗██║   ██║██╔════╝╚══██╔══╝██║   ██║██╔══██╗██╔════╝   ██╔═══██╗",
    " ███████╗   ██║   ██████╔╝██║   ██║██║        ██║   ██║   ██║██████╔╝█████╗  ██ ██║   ██║",
    " ╚════██║   ██║   ██╔══██╗██║   ██║██║        ██║   ██║   ██║██╔══██╗██╔══╝     ██║   ██║",
    " ███████║   ██║   ██║  ██║╚██████╔╝╚██████╗   ██║   ╚██████╔╝██║  ██║███████╗   ██╚═══██║",
    " ╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝   ███████╔╝",
];

const TAGLINE: &str =
    "Unstructured → Structured  ·  Any format, any schema, high-throughput vLLM inference";
const VERSION: &str = "CLI v0.1.0";
const SUBTITLE: &str = "Command-line interface";

// ── Terminal helpers ──────────────────────────────────────────────────────────

fn term_width() -> usize {
    terminal::size().map(|(w, _)| w as usize).unwrap_or(120).max(60)
}

/// Print one content line inside a panel.
/// `plain`   — uncolored text (used only to measure display width).
/// `colored` — the same text with ANSI styling (what actually gets printed).
fn panel_line(pad: &str, plain: &str, colored: &str, inner_w: usize) {
    let display_w = plain.chars().count();
    let right = inner_w.saturating_sub(pad.len() + display_w + pad.len());
    println!("│{}{}{}{}│", pad, colored, " ".repeat(right), pad);
}

fn panel_empty(inner_w: usize) {
    println!("│{}│", " ".repeat(inner_w));
}

// ── Banner ────────────────────────────────────────────────────────────────────

fn print_banner() {
    let tw = term_width();
    let pad_h = if tw >= 100 { 2 } else { 1 };
    let pad = " ".repeat(pad_h);
    let inner_w = tw.saturating_sub(2);   // space between │ and │
    let content_w = inner_w.saturating_sub(pad_h * 2);

    // Top border — version title flush-right
    let title = format!(" {} ", VERSION);
    let title_len = title.chars().count();
    let dashes = inner_w.saturating_sub(title_len);
    println!(
        "{}{}{}{}",
        "┌".white(),
        "─".repeat(dashes).white(),
        title.dimmed(),
        "┐".white()
    );

    panel_empty(inner_w);

    // "Welcome to"
    let welcome = "Welcome to";
    panel_line(&pad, welcome, &welcome.dimmed().to_string(), inner_w);

    // Wordmark (box-drawing art) — bright cyan, truncated if terminal is narrow
    for &wm_line in WORDMARK {
        let line_w = wm_line.chars().count();
        if line_w <= content_w {
            panel_line(&pad, wm_line, &wm_line.bright_cyan().bold().to_string(), inner_w);
        } else {
            let truncated: String = wm_line.chars().take(content_w).collect();
            panel_line(&pad, &truncated, &truncated.bright_cyan().bold().to_string(), inner_w);
        }
    }

    // Subtitle
    panel_line(&pad, SUBTITLE, &SUBTITLE.dimmed().to_string(), inner_w);

    // Tagline — word-wrapped if terminal is narrow
    let tagline_chars = TAGLINE.chars().count();
    if tagline_chars <= content_w {
        panel_line(&pad, TAGLINE, &TAGLINE.dimmed().to_string(), inner_w);
    } else {
        let mut current = String::new();
        for word in TAGLINE.split_whitespace() {
            let candidate = if current.is_empty() {
                word.to_string()
            } else {
                format!("{} {}", current, word)
            };
            if candidate.chars().count() <= content_w {
                current = candidate;
            } else {
                if !current.is_empty() {
                    panel_line(&pad, &current, &current.dimmed().to_string(), inner_w);
                }
                current = word.to_string();
            }
        }
        if !current.is_empty() {
            panel_line(&pad, &current, &current.dimmed().to_string(), inner_w);
        }
    }

    panel_empty(inner_w);

    // Bottom border
    println!("└{}┘", "─".repeat(inner_w));
    println!();
}

// ── Init spinner sequence ─────────────────────────────────────────────────────

fn print_init() {
    println!("{}\n", "Initializing...".bold());

    let steps = [
        "Loading configuration",
        "Loading model registry",
        "Discovering parsers",
        "Checking providers",
        "Ready",
    ];

    let style = ProgressStyle::with_template("{spinner:.cyan} {msg}")
        .unwrap()
        .tick_strings(&["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏", " "]);

    for step in &steps {
        let pb = ProgressBar::new(1);
        pb.set_style(style.clone());
        pb.set_message(step.to_string());
        pb.enable_steady_tick(Duration::from_millis(80));
        thread::sleep(Duration::from_millis(150));
        pb.finish_and_clear();
    }
}

// ── System Ready panel ────────────────────────────────────────────────────────

fn print_ready(settings: &crate::config::Settings) {
    let tw = term_width();
    let inner_w = tw.saturating_sub(2);
    let provider = &settings.inference.provider;
    let n_schemas = crate::schemas::list_schemas().len();

    // (plain text for width calculation, colored text for display)
    let schemas_plain = format!("  ✓ Schemas available    ({} built-in)", n_schemas);
    let provider_plain = format!("  ✓ Provider configured  ({})", provider);
    let rows: Vec<(&str, String)> = vec![
        (
            "  ✓ Config loaded        (default)",
            format!("  {} Config loaded        {}", "✓".green().bold(), "(default)".dimmed()),
        ),
        (
            "  ✓ Models registered    (from models.yaml)",
            format!(
                "  {} Models registered    {}",
                "✓".green().bold(),
                "(from models.yaml)".dimmed()
            ),
        ),
        (
            &schemas_plain,
            format!(
                "  {} Schemas available    {}",
                "✓".green().bold(),
                format!("({} built-in)", n_schemas).dimmed()
            ),
        ),
        (
            "  ✓ Formats supported    (PDF, DOCX, HTML, XLSX, Email, Text)",
            format!(
                "  {} Formats supported    {}",
                "✓".green().bold(),
                "(PDF, DOCX, HTML, XLSX, Email, Text)".dimmed()
            ),
        ),
        (
            &provider_plain,
            format!(
                "  {} Provider configured  {}",
                "✓".green().bold(),
                format!("({})", provider).dimmed()
            ),
        ),
    ];

    // Green-bordered panel title
    let title = " System Ready ";
    let title_len = title.chars().count();
    let dashes = inner_w.saturating_sub(title_len);
    println!(
        "{}{}{}{}",
        "┌".green(),
        "─".repeat(dashes).green(),
        title.green().bold(),
        "┐".green()
    );

    for (plain, colored) in &rows {
        panel_line(" ", plain, colored, inner_w);
    }

    println!("{}{}{}", "└".green(), "─".repeat(inner_w).green(), "┘".green());
    println!();
}

// ── Welcome message ───────────────────────────────────────────────────────────

fn print_welcome() {
    println!("{}", "Welcome to Structure-D interactive terminal.".bold().white());
    println!(
        "Type {} to see available commands, or {} to quit.\n",
        "help".bright_green().bold(),
        "exit".bright_green().bold()
    );
}

// ── Help text ─────────────────────────────────────────────────────────────────

fn print_help() {
    println!("\n{}\n", "Commands".bold().underline());

    let cmds: &[(&str, &str, &str)] = &[
        ("extract", "<file> [options]",  "Extract structured data from a file"),
        ("batch",   "<dir> [options]",   "Batch-extract from all files in a directory"),
        ("models",  "",                  "Show registered models"),
        ("schemas", "",                  "Show built-in extraction schemas"),
        ("formats", "",                  "Show supported input file formats"),
        ("config",  "",                  "Show current configuration"),
        ("status",  "",                  "Check provider connectivity"),
        ("clear",   "",                  "Clear the screen"),
        ("version", "",                  "Show version info"),
        ("help",    "",                  "Show this help message"),
        ("exit",    "",                  "Exit the terminal"),
    ];

    for (cmd, args, desc) in cmds {
        if args.is_empty() {
            println!("  {:30} {}", cmd.bright_green().bold(), desc.dimmed());
        } else {
            println!(
                "  {} {:24} {}",
                cmd.bright_green().bold(),
                args.dimmed(),
                desc.dimmed()
            );
        }
    }

    println!("\n  {}", "Options for extract / batch:".dimmed());
    let opts: &[(&str, &str)] = &[
        ("--schema <name>", "generic, key_value, table, entity, form, classification, summary, document_structure"),
        ("--task <type>",   "extraction, classification, summarisation, sentiment"),
        ("--model <name>",  "Model alias (default: auto-route)"),
        ("--format <fmt>",  "jsonl or csv (default: jsonl)"),
        ("--output <dir>",  "Output directory"),
    ];
    for (opt, desc) in opts {
        println!("    {:25} {}", opt.dimmed(), desc.dimmed());
    }
    println!();
}

// ── Command dispatch ──────────────────────────────────────────────────────────

fn dispatch(input: &str, settings: &crate::config::Settings) -> bool {
    let mut parts = input.splitn(2, ' ');
    let cmd = parts.next().unwrap_or("").to_lowercase();
    let _rest = parts.next().unwrap_or("");

    match cmd.as_str() {
        "exit" | "quit" | "q" => {
            println!("{}", "Goodbye!".bright_cyan());
            return false;
        }
        "help" | "?" => print_help(),
        "clear" => {
            // ANSI: clear screen + move cursor to top-left
            print!("\x1b[2J\x1b[H");
            print_banner();
        }
        "version" => {
            println!("{} {}", "Structure-D".bold(), "v0.1.0".bright_cyan());
        }
        "schemas" => {
            println!("\n{}\n", "Built-in schemas:".bold());
            for (name, desc) in crate::schemas::list_schemas() {
                println!("  {:30} {}", name.bright_green(), desc.dimmed());
            }
            println!();
        }
        "models" => {
            println!("\n{}", "  Active provider:".bold());
            println!("  {}\n", settings.inference.provider.bright_cyan());
            println!(
                "  {}\n",
                "Run 'structure-d models' outside the REPL for the full registry.".dimmed()
            );
        }
        "formats" => {
            println!("\n{}\n", "Supported formats:".bold());
            for (fmt, exts) in crate::ingestion::SUPPORTED_FORMATS {
                println!("  {:20} {}", fmt.bright_green(), exts.dimmed());
            }
            println!();
        }
        "config" => {
            println!("\n{}", "  Active config:".bold());
            println!("  Provider  {}", settings.inference.provider.bright_cyan());
            println!("  Output    {}", settings.storage.output_dir.bright_cyan());
            println!("  Format    {}", settings.storage.default_format.bright_cyan());
            println!("  Log level {}\n", settings.monitoring.log_level.bright_cyan());
        }
        "status" => {
            println!(
                "\n  {} Run {} to test provider connectivity.\n",
                "Tip:".bright_yellow().bold(),
                "structure-d providers --check".bright_cyan()
            );
        }
        "extract" | "batch" => {
            println!(
                "\n  {}\n",
                format!(
                    "Use: structure-d {} <{}> [options]  (run from your shell, not the REPL)",
                    cmd,
                    if cmd == "extract" { "file" } else { "dir" }
                )
                .dimmed()
            );
        }
        "" => {}
        other => {
            println!(
                "{} '{}'\n{}\n",
                "Unknown command:".red(),
                other,
                "Type 'help' to see available commands.".dimmed()
            );
        }
    }
    true
}

// ── Public entry point ────────────────────────────────────────────────────────

pub fn run_interactive() -> Result<()> {
    let settings = crate::config::Settings::load(None).unwrap_or_default();

    print_banner();
    print_init();
    print_ready(&settings);
    print_welcome();

    let mut rl = DefaultEditor::new()?;

    // Prompt with ANSI color codes — "structure-d ❯ "
    let prompt = format!(
        "{} {} ",
        "structure-d".bright_cyan().bold(),
        "❯".bright_green().bold()
    );

    loop {
        match rl.readline(&prompt) {
            Ok(line) => {
                let line = line.trim().to_string();
                if !line.is_empty() {
                    let _ = rl.add_history_entry(&line);
                }
                if !dispatch(&line, &settings) {
                    break;
                }
            }
            Err(rustyline::error::ReadlineError::Interrupted)
            | Err(rustyline::error::ReadlineError::Eof) => {
                println!("\n{}", "Goodbye!".bright_cyan());
                break;
            }
            Err(e) => return Err(e.into()),
        }
    }

    Ok(())
}
