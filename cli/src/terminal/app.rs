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

// ── Provider readiness assessment ────────────────────────────────────────────

#[derive(PartialEq)]
enum Readiness {
    /// API key confirmed present in config or env var.
    Ready,
    /// Config name is set but key / endpoint is not confirmed.
    Unverified,
    /// No key and no meaningful configuration — user action required.
    NotConfigured,
}

struct ProviderInfo {
    readiness: Readiness,
    /// One-line summary for the "Provider" row (plain text).
    provider_desc: String,
    /// One-line summary for the "Model" row (plain text).
    model_desc: String,
}

/// Check whether the user has a personal config file saved by `configure`.
fn user_config_exists() -> bool {
    dirs::home_dir()
        .map(|h| h.join(".structure-d").join("config.yaml").exists())
        .unwrap_or(false)
}

/// Assess the configured provider against actual credentials / defaults.
fn assess_provider(settings: &crate::config::Settings) -> ProviderInfo {
    match settings.inference.provider.as_str() {
        "openai" => {
            let has_key = settings.inference.openai.api_key.is_some()
                || std::env::var("OPENAI_API_KEY").is_ok();
            ProviderInfo {
                readiness: if has_key { Readiness::Ready } else { Readiness::NotConfigured },
                provider_desc: if has_key {
                    "openai · API key set".into()
                } else {
                    "openai · no API key — run 'configure'".into()
                },
                model_desc: settings.inference.openai.model.clone(),
            }
        }
        "anthropic" => {
            let has_key = settings.inference.anthropic.api_key.is_some()
                || std::env::var("ANTHROPIC_API_KEY").is_ok();
            ProviderInfo {
                readiness: if has_key { Readiness::Ready } else { Readiness::NotConfigured },
                provider_desc: if has_key {
                    "anthropic · API key set".into()
                } else {
                    "anthropic · no API key — run 'configure'".into()
                },
                model_desc: settings.inference.anthropic.model.clone(),
            }
        }
        "gemini" => {
            let has_key = settings.inference.gemini.api_key.is_some()
                || std::env::var("GEMINI_API_KEY").is_ok()
                || std::env::var("GOOGLE_API_KEY").is_ok();
            ProviderInfo {
                readiness: if has_key { Readiness::Ready } else { Readiness::NotConfigured },
                provider_desc: if has_key {
                    "gemini · API key set".into()
                } else {
                    "gemini · no API key — run 'configure'".into()
                },
                model_desc: settings.inference.gemini.model.clone(),
            }
        }
        // Local servers: endpoint is known but reachability is not confirmed at
        // startup (we skip the HTTP round-trip to keep the REPL instant).
        // Users can run `status --check` to probe the endpoint explicitly.
        "vllm" => ProviderInfo {
            readiness: Readiness::Unverified,
            provider_desc: format!(
                "vllm · {} · not verified (run 'status --check')",
                settings.inference.vllm.api_base
            ),
            model_desc: format!(
                "{} · endpoint must be reachable to use",
                settings.inference.vllm.model
            ),
        },
        "ollama" => ProviderInfo {
            readiness: Readiness::Unverified,
            provider_desc: format!(
                "ollama · {} · not verified (run 'status --check')",
                settings.inference.ollama.base_url
            ),
            model_desc: format!(
                "{} · run 'status --check' to verify",
                settings.inference.ollama.model
            ),
        },
        other => ProviderInfo {
            readiness: Readiness::NotConfigured,
            provider_desc: format!("{} · unrecognised — run 'configure'", other),
            model_desc: "—".into(),
        },
    }
}

// ── System Ready panel ────────────────────────────────────────────────────────

fn print_ready(settings: &crate::config::Settings) {
    let tw = term_width();
    let inner_w = tw.saturating_sub(2);
    let n_schemas = crate::schemas::list_schemas().len();

    let pi = assess_provider(settings);

    // Config source description
    let config_note = if user_config_exists() {
        "~/.structure-d/config.yaml".to_string()
    } else {
        "default · run 'configure' to set your provider".to_string()
    };

    // Choose icons based on readiness
    let tick  = "✓".green().bold().to_string();
    let warn  = "⚠".yellow().bold().to_string();
    let dash  = "–".bright_black().to_string();

    let (p_icon_plain, p_icon_col) = match pi.readiness {
        Readiness::Ready         => ("✓", tick.clone()),
        Readiness::NotConfigured => ("⚠", warn.clone()),
        Readiness::Unverified    => ("–", dash.clone()),
    };
    let (m_icon_plain, m_icon_col) = match pi.readiness {
        Readiness::Ready         => ("✓", tick.clone()),
        Readiness::NotConfigured => ("⚠", warn.clone()),
        Readiness::Unverified    => ("–", dash.clone()),
    };

    // Build (plain, colored) row pairs — plain is used only for width maths
    let rows: Vec<(String, String)> = vec![
        (
            format!("  ✓ Config     ({})", config_note),
            format!("  {} Config     {}", tick, format!("({})", config_note).dimmed()),
        ),
        (
            format!("  ✓ Schemas    ({} built-in)", n_schemas),
            format!("  {} Schemas    {}", tick, format!("({} built-in)", n_schemas).dimmed()),
        ),
        (
            "  ✓ Formats    (PDF, DOCX, HTML, XLSX, Email, Text)".into(),
            format!("  {} Formats    {}", tick, "(PDF, DOCX, HTML, XLSX, Email, Text)".dimmed()),
        ),
        (
            format!("  {} Provider   ({})", p_icon_plain, pi.provider_desc),
            format!("  {} Provider   {}", p_icon_col, format!("({})", pi.provider_desc).dimmed()),
        ),
        (
            format!("  {} Model      ({})", m_icon_plain, pi.model_desc),
            format!("  {} Model      {}", m_icon_col, format!("({})", pi.model_desc).dimmed()),
        ),
    ];

    // Panel border colour and title depend on overall readiness
    let is_ready = pi.readiness == Readiness::Ready;
    let title    = if is_ready { " System Ready " } else { " System Initialized " };
    let title_len = title.chars().count();
    let dashes   = inner_w.saturating_sub(title_len);

    if is_ready {
        println!("{}{}{}{}", "┌".green(),  "─".repeat(dashes).green(),  title.green().bold().to_string(),  "┐".green());
    } else {
        println!("{}{}{}{}", "┌".yellow(), "─".repeat(dashes).yellow(), title.yellow().bold().to_string(), "┐".yellow());
    }

    for (plain, colored) in &rows {
        panel_line(" ", plain, colored, inner_w);
    }

    if is_ready {
        println!("{}{}{}", "└".green(),  "─".repeat(inner_w).green(),  "┘".green());
    } else {
        println!("{}{}{}", "└".yellow(), "─".repeat(inner_w).yellow(), "┘".yellow());
    }
    println!();

    // Post-panel hint when the user still needs to configure something
    match pi.readiness {
        Readiness::NotConfigured => println!(
            "  {} Run {} to set your LLM provider and API key.\n",
            "→".bright_cyan(),
            "'configure'".bright_cyan().bold()
        ),
        Readiness::Unverified => println!(
            "  {} Run {} to confirm the endpoint is reachable before extracting.\n",
            "→".bright_cyan(),
            "'status --check'".bright_cyan().bold()
        ),
        Readiness::Ready => {}
    }
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
        ("--output-format <fmt>",  "jsonl or csv (default: jsonl)"),
        ("--output <dir>",  "Output directory"),
    ];
    for (opt, desc) in opts {
        println!("    {:25} {}", opt.dimmed(), desc.dimmed());
    }
    println!();
}

// ── File / directory picker ───────────────────────────────────────────────────

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

/// Save provider + model (+ API key / endpoint) to ~/.structure-d/config.yaml
fn configure_provider() {
    use dialoguer::{theme::ColorfulTheme, Input, Select};
    let theme = ColorfulTheme::default();

    println!();

    // ── Step 1: provider ─────────────────────────────────────────────────────
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

    // ── Step 2: API key (cloud providers only) ────────────────────────────────
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
                format!("  API key [env {} already set — press Enter to keep]", env_var)
            };
            let key: String = Input::with_theme(&theme)
                .with_prompt(&hint)
                .allow_empty(true)
                .interact_text()
                .unwrap_or_default();
            if key.is_empty() && !placeholder.is_empty() {
                None // keep existing env var
            } else if key.is_empty() {
                println!("  {} No API key provided — skipped.\n", "!".bright_yellow());
                return;
            } else {
                Some(key)
            }
        }
        _ => None,
    };

    // ── Step 3: model selection ───────────────────────────────────────────────
    // Each entry is (display label, model id). An empty id means "Custom…".
    let model_menu: &[(&str, &str)] = match provider {
        "openai" => &[
            ("gpt-4o              (recommended, multimodal)", "gpt-4o"),
            ("gpt-4o-mini         (default · fast & cheap)",  "gpt-4o-mini"),
            ("gpt-4-turbo         (legacy GPT-4 turbo)",      "gpt-4-turbo"),
            ("gpt-3.5-turbo       (fastest, cheapest)",       "gpt-3.5-turbo"),
            ("Custom…",                                        ""),
        ],
        "anthropic" => &[
            ("claude-opus-4-5     (most capable)",            "claude-opus-4-5"),
            ("claude-sonnet-4-6   (default · balanced)",      "claude-sonnet-4-6"),
            ("claude-haiku-3-5    (fastest, cheapest)",       "claude-haiku-3-5"),
            ("Custom…",                                        ""),
        ],
        "gemini" => &[
            ("gemini-2.0-flash    (default · fast)",          "gemini-2.0-flash"),
            ("gemini-1.5-pro      (most capable)",            "gemini-1.5-pro"),
            ("gemini-1.5-flash    (fast, efficient)",         "gemini-1.5-flash"),
            ("Custom…",                                        ""),
        ],
        _ => &[], // vllm / ollama: free-text entry below
    };

    // Default selection index — points to the "balanced" / recommended model
    let default_model_idx: usize = match provider {
        "openai"    => 1, // gpt-4o-mini
        "anthropic" => 1, // claude-sonnet-4-6
        "gemini"    => 0, // gemini-2.0-flash
        _           => 0,
    };

    let selected_model: String = if !model_menu.is_empty() {
        let labels: Vec<&str> = model_menu.iter().map(|(l, _)| *l).collect();
        let mi = match Select::with_theme(&theme)
            .with_prompt("  Model")
            .items(&labels)
            .default(default_model_idx)
            .interact_opt()
        {
            Ok(Some(i)) => i,
            _ => return,
        };
        let (_, model_id) = model_menu[mi];
        if model_id.is_empty() {
            // "Custom…" — free-text entry
            Input::with_theme(&theme)
                .with_prompt("  Model name")
                .interact_text()
                .unwrap_or_default()
        } else {
            model_id.to_string()
        }
    } else {
        // vllm / ollama — just a text field with a sensible default
        let default_val = match provider {
            "vllm"   => "meta-llama/Meta-Llama-3.1-8B-Instruct",
            "ollama" => "llama3.1",
            _        => "",
        };
        Input::with_theme(&theme)
            .with_prompt("  Model name")
            .default(default_val.to_string())
            .interact_text()
            .unwrap_or_else(|_| default_val.to_string())
    };

    // ── Step 4: endpoint (local providers only) ───────────────────────────────
    let endpoint: Option<String> = match provider {
        "vllm" => {
            let ep: String = Input::with_theme(&theme)
                .with_prompt("  vLLM API base URL")
                .default("http://localhost:8000/v1".to_string())
                .interact_text()
                .unwrap_or_else(|_| "http://localhost:8000/v1".to_string());
            Some(ep)
        }
        "ollama" => {
            let ep: String = Input::with_theme(&theme)
                .with_prompt("  Ollama base URL")
                .default("http://localhost:11434".to_string())
                .interact_text()
                .unwrap_or_else(|_| "http://localhost:11434".to_string());
            Some(ep)
        }
        _ => None,
    };

    // ── Step 5: write ~/.structure-d/config.yaml ──────────────────────────────
    let config_dir = dirs::home_dir().unwrap_or_default().join(".structure-d");
    let _ = std::fs::create_dir_all(&config_dir);
    let config_path = config_dir.join("config.yaml");

    let provider_block = match provider {
        "openai" => {
            let key_line = api_key
                .as_ref()
                .map(|k| format!("    api_key: \"{}\"\n", k))
                .unwrap_or_default();
            format!("  openai:\n{}    model: \"{}\"\n", key_line, selected_model)
        }
        "anthropic" => {
            let key_line = api_key
                .as_ref()
                .map(|k| format!("    api_key: \"{}\"\n", k))
                .unwrap_or_default();
            format!("  anthropic:\n{}    model: \"{}\"\n", key_line, selected_model)
        }
        "gemini" => {
            let key_line = api_key
                .as_ref()
                .map(|k| format!("    api_key: \"{}\"\n", k))
                .unwrap_or_default();
            format!("  gemini:\n{}    model: \"{}\"\n", key_line, selected_model)
        }
        "vllm" => {
            let ep = endpoint.unwrap_or_else(|| "http://localhost:8000/v1".to_string());
            format!("  vllm:\n    api_base: \"{}\"\n    model: \"{}\"\n", ep, selected_model)
        }
        "ollama" => {
            let ep = endpoint.unwrap_or_else(|| "http://localhost:11434".to_string());
            format!("  ollama:\n    base_url: \"{}\"\n    model: \"{}\"\n", ep, selected_model)
        }
        _ => String::new(),
    };

    let yaml = format!(
        "# Structure-D user config — generated by `configure`\ninference:\n  provider: \"{}\"\n{}",
        provider, provider_block
    );

    match std::fs::write(&config_path, &yaml) {
        Ok(_) => println!(
            "\n  {} Saved → {}\n  {} Provider: {}   Model: {}\n  {} Restart the terminal for changes to take effect.\n",
            "✓".bright_green().bold(),
            config_path.display().to_string().dimmed(),
            "·".dimmed(),
            provider.bright_cyan().bold(),
            selected_model.bright_cyan().bold(),
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
        "\n  {} extract {}  --schema {}  --output-format {}  --output {}\n",
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
            "--output-format",
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
        "\n  {} batch {}  --schema {}  --output-format {}\n",
        "Running:".bright_cyan().bold(),
        dir.bright_white(),
        schema.bright_white(),
        fmt.bright_white(),
    );

    let exe = std::env::current_exe().unwrap_or_else(|_| std::path::PathBuf::from("structure-d"));
    let _ = std::process::Command::new(exe)
        .args(["batch", &dir, "--schema", schema, "--output-format", fmt])
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
