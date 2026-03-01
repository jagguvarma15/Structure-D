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
        ("upload",     "",                 "Open file picker → extract → save to data/output/"),
        ("configure",  "",                 "Set LLM provider and API key"),
        ("extract",  "<file> [options]",  "Extract a specific file (or pick if no args)"),
        ("batch",    "<dir> [options]",   "Batch-extract from all files in a directory"),
        ("models",   "",                  "Show registered models"),
        ("schemas", "",                  "Show built-in extraction schemas"),
        ("formats", "",                  "Show supported input file formats"),
        ("config",  "",                  "Show current configuration"),
        ("status",  "[--check]",          "Show provider status (--check to ping)"),
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

// ── File / directory picker ───────────────────────────────────────────────────

const SUPPORTED_EXTS: &[&str] = &[
    "pdf", "docx", "xlsx", "xls", "pptx", "html", "htm", "eml", "txt", "md", "csv",
];

/// Scan `data/input/` for supported files.
/// Returns (display_label, absolute_path) pairs sorted by label.
fn collect_input_files() -> Vec<(String, std::path::PathBuf)> {
    let cwd = std::env::current_dir().unwrap_or_default();
    let input_dir = cwd.join("data").join("input");
    let mut files: Vec<(String, std::path::PathBuf)> = Vec::new();

    if let Ok(rd) = std::fs::read_dir(&input_dir) {
        for entry in rd.filter_map(|e| e.ok()) {
            let path = entry.path();
            if !path.is_file() { continue; }
            let ext = path.extension().and_then(|x| x.to_str()).unwrap_or("").to_lowercase();
            if !SUPPORTED_EXTS.contains(&ext.as_str()) { continue; }
            files.push((entry.file_name().to_string_lossy().to_string(), path));
        }
    }

    files.sort_by(|a, b| a.0.cmp(&b.0));
    files
}

/// Build output path: `data/output/<stem>_<schema>_<YYYY-MM-DD_HH-MM-SS>.<ext>`
fn make_output_path(file: &std::path::Path, schema: &str, fmt: &str) -> std::path::PathBuf {
    use chrono::Local;
    let stem = file.file_stem().and_then(|s| s.to_str()).unwrap_or("document");
    let ts = Local::now().format("%Y-%m-%d_%H-%M-%S").to_string();
    let name = format!("{}_{}_{}.{}", stem, schema, ts, fmt);
    let out_dir = std::env::current_dir().unwrap_or_default().join("data").join("output");
    let _ = std::fs::create_dir_all(&out_dir);
    out_dir.join(name)
}

/// Save provider + API key to ~/.structure-d/config.yaml
fn configure_provider() {
    use dialoguer::{theme::ColorfulTheme, Input, Select};
    let theme = ColorfulTheme::default();

    println!();

    let providers = ["openai", "anthropic", "gemini", "ollama", "vllm"];
    let pi = match Select::with_theme(&theme)
        .with_prompt("  Provider")
        .items(&providers)
        .default(0)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => return,
    };
    let provider = providers[pi];

    // API key prompt (not needed for ollama/vllm)
    let api_key: Option<String> = match provider {
        "openai" | "anthropic" | "gemini" => {
            let env_var = match provider {
                "openai"    => "OPENAI_API_KEY",
                "anthropic" => "ANTHROPIC_API_KEY",
                _           => "GEMINI_API_KEY",
            };
            let placeholder = std::env::var(env_var).unwrap_or_default();
            let hint = if placeholder.is_empty() {
                format!("  API key (or set {} env var)", env_var)
            } else {
                format!("  API key [env {} already set, press Enter to keep]", env_var)
            };
            let key: String = Input::with_theme(&theme)
                .with_prompt(&hint)
                .allow_empty(true)
                .interact_text()
                .unwrap_or_default();
            if key.is_empty() && !placeholder.is_empty() {
                None // keep env var
            } else if key.is_empty() {
                println!("  {} No API key provided — skipped.\n", "!".bright_yellow());
                return;
            } else {
                Some(key)
            }
        }
        _ => None,
    };

    // Write ~/.structure-d/config.yaml
    let config_dir = dirs::home_dir()
        .unwrap_or_default()
        .join(".structure-d");
    let _ = std::fs::create_dir_all(&config_dir);
    let config_path = config_dir.join("config.yaml");

    let key_line = match (provider, &api_key) {
        ("openai",    Some(k)) => format!("  openai:\n    api_key: \"{}\"\n", k),
        ("anthropic", Some(k)) => format!("  anthropic:\n    api_key: \"{}\"\n", k),
        ("gemini",    Some(k)) => format!("  gemini:\n    api_key: \"{}\"\n", k),
        _ => String::new(),
    };

    let yaml = format!(
        "# Structure-D user config — generated by `configure`\ninference:\n  provider: \"{}\"\n{}",
        provider, key_line
    );

    match std::fs::write(&config_path, &yaml) {
        Ok(_) => println!(
            "\n  {} Saved to {}\n  {} Restart the REPL for changes to take effect.\n",
            "✓".bright_green().bold(),
            config_path.display().to_string().dimmed(),
            "→".bright_cyan(),
        ),
        Err(e) => println!("\n  {} Could not save config: {}\n", "✗".red(), e),
    }
}

/// Open a native file-picker dialog.
/// Works on macOS (Finder), Windows (Explorer), and Linux (GTK / xdg-portal).
fn open_file_dialog() -> Option<std::path::PathBuf> {
    rfd::FileDialog::new()
        .set_title("Select a document to extract")
        .add_filter(
            "Documents",
            &["pdf", "docx", "xlsx", "xls", "pptx", "html", "htm", "eml", "txt", "md", "csv"],
        )
        .pick_file()
}

/// Native file dialog → schema → format → run extract.
fn pick_and_run_upload() {
    use dialoguer::{theme::ColorfulTheme, Select};
    let theme = ColorfulTheme::default();

    println!("\n  {} Opening file picker…\n", "↑".bright_cyan());

    let file_path = match open_file_dialog() {
        Some(p) => p,
        None => {
            println!("  {}\n", "No file selected.".dimmed());
            return;
        }
    };

    // Step 2 — schema
    let schemas: Vec<&str> = crate::schemas::SCHEMA_NAMES.to_vec();
    let si = match Select::with_theme(&theme)
        .with_prompt("  Schema")
        .items(&schemas)
        .default(0)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => return,
    };
    let schema = schemas[si];

    // Step 3 — output format
    let formats = ["jsonl", "csv"];
    let fi2 = match Select::with_theme(&theme)
        .with_prompt("  Output format")
        .items(&formats)
        .default(0)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => return,
    };
    let fmt = formats[fi2];

    let output = make_output_path(&file_path, schema, fmt);

    println!(
        "\n  {} extract {}  --schema {}  --format {}  --output {}\n",
        "Running:".bright_cyan().bold(),
        file_path.display().to_string().bright_white(),
        schema.bright_white(),
        fmt.bright_white(),
        output.display().to_string().dimmed(),
    );

    let exe = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("structure-d"));
    let status = std::process::Command::new(&exe)
        .args([
            "extract",
            file_path.to_str().unwrap_or(""),
            "--schema",
            schema,
            "--format",
            fmt,
            "--output",
            output.to_str().unwrap_or("data/output/result"),
        ])
        .status();

    match status {
        Ok(s) if s.success() => println!(
            "\n  {} Saved → {}\n",
            "✓".bright_green().bold(),
            output.display()
        ),
        _ => println!(
            "\n  {} Extraction failed. Run {} to set your LLM provider and API key.\n",
            "✗".red().bold(),
            "configure".bright_cyan()
        ),
    }
    println!();
}

fn pick_and_run_batch() {
    use dialoguer::{theme::ColorfulTheme, Select};
    let theme = ColorfulTheme::default();
    let cwd = std::env::current_dir().unwrap_or_default();

    // Always offer input/ data/ if they exist, then other subdirs
    let mut dirs: Vec<String> = Vec::new();
    for name in &["input", "data"] {
        if cwd.join(name).is_dir() {
            dirs.push(name.to_string());
        }
    }
    if let Ok(rd) = std::fs::read_dir(&cwd) {
        let mut others: Vec<String> = rd
            .filter_map(|e: std::io::Result<std::fs::DirEntry>| e.ok())
            .filter(|e| e.path().is_dir())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .filter(|n| !n.starts_with('.') && n != "input" && n != "data" && n != "output" && n != "target")
            .collect();
        others.sort();
        dirs.extend(others);
    }
    dirs.push(". (current directory)".to_string());

    println!();

    let di = match Select::with_theme(&theme)
        .with_prompt("  Select directory")
        .items(&dirs)
        .default(0)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => return,
    };
    let dir = if dirs[di] == ". (current directory)" {
        ".".to_string()
    } else {
        dirs[di].clone()
    };

    let schemas: Vec<&str> = crate::schemas::SCHEMA_NAMES.to_vec();
    let si = match Select::with_theme(&theme)
        .with_prompt("  Schema")
        .items(&schemas)
        .default(0)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => return,
    };
    let schema = schemas[si];

    let formats = ["jsonl", "csv"];
    let fi = match Select::with_theme(&theme)
        .with_prompt("  Output format")
        .items(&formats)
        .default(0)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => return,
    };
    let fmt = formats[fi];

    println!(
        "\n  {} batch {}  --schema {}  --format {}\n",
        "Running:".bright_cyan().bold(),
        dir.bright_white(),
        schema.bright_white(),
        fmt.bright_white(),
    );

    let exe = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("structure-d"));
    let _ = std::process::Command::new(exe)
        .args(["batch", &dir, "--schema", schema, "--format", fmt])
        .status();
    println!();
}

// ── Command dispatch ──────────────────────────────────────────────────────────

fn dispatch(input: &str, settings: &crate::config::Settings) -> bool {
    let mut parts = input.splitn(2, ' ');
    let cmd = parts.next().unwrap_or("").to_lowercase();
    let rest = parts.next().unwrap_or("").trim();

    match cmd.as_str() {
        "exit" | "quit" | "q" => {
            println!("{}", "Goodbye!".bright_cyan());
            return false;
        }
        "help" | "?" => print_help(),
        "clear" => {
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
            let exe = std::env::current_exe()
                .unwrap_or_else(|_| std::path::PathBuf::from("structure-d"));
            let rest = rest.trim();
            if rest == "--check" || rest == "-c" {
                let _ = std::process::Command::new(exe)
                    .args(["providers", "--check"])
                    .status();
            } else {
                let _ = std::process::Command::new(exe)
                    .arg("providers")
                    .status();
            }
        }
        // ── upload / configure / extract / batch ─────────────────────────────
        "upload" | "u" => pick_and_run_upload(),
        "configure" | "config set" => configure_provider(),
        "extract" => {
            if rest.is_empty() {
                pick_and_run_upload();
            } else {
                let exe = std::env::current_exe()
                    .unwrap_or_else(|_| std::path::PathBuf::from("structure-d"));
                let _ = std::process::Command::new(exe)
                    .arg("extract")
                    .args(rest.split_whitespace())
                    .status();
                println!();
            }
        }
        "batch" => {
            if rest.is_empty() {
                pick_and_run_batch();
            } else {
                let exe = std::env::current_exe()
                    .unwrap_or_else(|_| std::path::PathBuf::from("structure-d"));
                let _ = std::process::Command::new(exe)
                    .arg("batch")
                    .args(rest.split_whitespace())
                    .status();
                println!();
            }
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
