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
const SUBTITLE: &str = "Command-line interface";

/// Full version string shown in the banner title.
///
/// On a clean tagged release → `"CLI v0.2.0"`
/// After new commits         → `"CLI v0.2.0 (v0.2.0-3-gabcdef)"`
fn cli_version() -> String {
    let base = env!("CARGO_PKG_VERSION");
    let desc = env!("GIT_DESCRIBE");
    let clean_tag = format!("v{}", base);
    if desc == clean_tag || desc == base {
        format!("CLI v{}", base)
    } else {
        format!("CLI v{} ({})", base, desc)
    }
}

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
    let title = format!(" {} ", cli_version());
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

/// Shows which `structure-d` binary is running (stdout) so it’s obvious when the shell’s PATH
/// points at an older install instead of `./target/release/structure-d` from this repo.
fn print_running_exe_line() {
    match std::env::current_exe() {
        Ok(p) => println!(
            "  {} {}\n",
            "Executable:".dimmed(),
            p.display().to_string().bright_white()
        ),
        Err(_) => println!("  {}\n", "(could not resolve current executable path)".dimmed()),
    }
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
        ("--output-format <fmt>",  "jsonl, csv, md, or parquet (default: jsonl)"),
        ("--output <dir>",  "Output directory"),
    ];
    for (opt, desc) in opts {
        println!("    {:25} {}", opt.dimmed(), desc.dimmed());
    }

    println!(
        "\n  {}",
        "Troubleshooting upload:".bold()
    );
    println!(
        "    If {} shows {} / {} arrow menus with only two formats, you are not running this repo’s binary.",
        "upload".bright_green(),
        "? … ›".dimmed(),
        "❯".green()
    );
    println!(
        "    Build from the repo root, then run the local binary explicitly:\n    {}",
        "cargo build --release && ./target/release/structure-d".bright_cyan()
    );
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

/// Built-in schema choice for interactive upload/batch.
///
/// Avoids [`dialoguer::Select`]: it sizes the visible window from **terminal row count**, so in
/// a short integrated terminal only ~two options appear at once and the rest look “missing”.
///
/// Uses the same [`DefaultEditor`] as the REPL: `std::io::stdin().read_line` fights with
/// rustyline’s TTY handling, so sub-prompts can swallow input or never show `md` as selectable.
fn prompt_builtin_schema_interactive(rl: &mut DefaultEditor) -> Option<&'static str> {
    let names = crate::schemas::SCHEMA_NAMES;
    println!();
    println!("  {}", "Schema (built-in)".bold());
    for (i, name) in names.iter().enumerate() {
        println!("    {:>2}  {}", i + 1, name);
    }
    let prompt = format!("  Enter 1-{} [default: 1]: ", names.len());
    let line = rl.readline(&prompt).ok()?;
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return Some(names[0]);
    }
    let n: usize = trimmed.parse().ok()?;
    if !(1..=names.len()).contains(&n) {
        return None;
    }
    Some(names[n - 1])
}

/// `--output-format` for interactive upload/batch (`jsonl` | `csv` | `md` | `parquet`).
///
/// Same rationale as [`prompt_builtin_schema_interactive`]: no `Select`, so every choice is
/// listed. The CLI flag value remains `md` (not `markdown`).
fn prompt_output_format_interactive(rl: &mut DefaultEditor) -> Option<&'static str> {
    const VALUES: &[&str] = &["jsonl", "csv", "md", "parquet"];
    println!();
    println!("  {}", "Output format".bold());
    println!(
        "  {}",
        "1=jsonl  ·  2=csv  ·  3=md  ·  4=parquet"
            .dimmed()
    );
    println!("     1  JSON Lines (.jsonl)");
    println!("     2  CSV (.csv)");
    println!("     3  Markdown (.md)");
    println!("     4  Parquet (.parquet)");
    let line = rl.readline("  Enter 1-4 [default: 1]: ").ok()?;
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return Some(VALUES[0]);
    }
    let n: usize = trimmed.parse().ok()?;
    if !(1..=4).contains(&n) {
        return None;
    }
    Some(VALUES[n - 1])
}

/// Mask an API key for safe display: `sk-ant-...abcd`
fn mask_key(key: &str) -> String {
    if key.len() > 12 {
        format!("{}···{}", &key[..6], &key[key.len()-4..])
    } else {
        "••••••••".to_string()
    }
}

/// Save / update provider + model (+ API key / endpoint) in ~/.structure-d/config.yaml.
///
/// If the selected provider is already configured the user is shown what is
/// currently saved and asked *what* they want to change (model, key, both, or
/// nothing). Only the chosen fields are re-prompted; everything else is carried
/// forward from the existing config.  ESC or "Cancel" at any menu exits cleanly.
fn configure_provider() {
    use dialoguer::{theme::ColorfulTheme, Input, Select};
    let theme = ColorfulTheme::default();

    println!();

    // Load current settings so we can show existing values and pre-select menus.
    let current = crate::config::Settings::load(None).unwrap_or_default();

    // ── Step 1: choose provider (pre-select whatever is active) ──────────────
    let providers = ["openai", "anthropic", "gemini", "ollama", "vllm"];
    let current_idx = providers
        .iter()
        .position(|p| *p == current.inference.provider)
        .unwrap_or(0);

    let pi = match Select::with_theme(&theme)
        .with_prompt("  Provider")
        .items(&providers)
        .default(current_idx)
        .interact_opt()
    {
        Ok(Some(i)) => i,
        _ => { println!("  {}\n", "Cancelled.".dimmed()); return; }
    };
    let provider = providers[pi];

    let is_cloud = matches!(provider, "openai" | "anthropic" | "gemini");
    let is_local = matches!(provider, "vllm" | "ollama");

    // ── Step 2: pull existing saved values for this provider ─────────────────
    // These come from the config file (not env vars) so we can safely rewrite them.
    let (saved_key, saved_model, saved_endpoint): (Option<String>, String, Option<String>) =
        match provider {
            "openai"    => (current.inference.openai.api_key.clone(),
                            current.inference.openai.model.clone(), None),
            "anthropic" => (current.inference.anthropic.api_key.clone(),
                            current.inference.anthropic.model.clone(), None),
            "gemini"    => (current.inference.gemini.api_key.clone(),
                            current.inference.gemini.model.clone(), None),
            "vllm"      => (None, current.inference.vllm.model.clone(),
                            Some(current.inference.vllm.api_base.clone())),
            "ollama"    => (None, current.inference.ollama.model.clone(),
                            Some(current.inference.ollama.base_url.clone())),
            _           => (None, String::new(), None),
        };

    // Also check process env vars for cloud keys (they count as "configured").
    let env_key: Option<String> = match provider {
        "openai"    => std::env::var("OPENAI_API_KEY").ok(),
        "anthropic" => std::env::var("ANTHROPIC_API_KEY").ok(),
        "gemini"    => std::env::var("GEMINI_API_KEY").ok()
                           .or_else(|| std::env::var("GOOGLE_API_KEY").ok()),
        _           => None,
    };

    let effective_key = saved_key.as_ref().or(env_key.as_ref());

    // Provider is "already configured" when:
    //   cloud  → a key exists (saved or env)
    //   local  → user has a config file AND it points at this provider
    let is_configured = if is_cloud {
        effective_key.is_some()
    } else {
        user_config_exists() && current.inference.provider == provider
    };

    // ── Step 3: if configured, ask what to change (ESC / Cancel exits) ───────
    // Flags: (need_key, need_model, need_endpoint)
    let (need_key, need_model, need_endpoint): (bool, bool, bool) = if is_configured {
        if is_cloud {
            let key_display = effective_key.map(|k| mask_key(k)).unwrap_or_default();
            println!(
                "\n  {} Currently:  {}  ·  model {}  ·  key {}\n",
                "·".bright_cyan(),
                provider.bright_cyan().bold(),
                saved_model.bright_white(),
                key_display.dimmed(),
            );
            let actions = [
                "Change model",
                "Change API key",
                "Change model and API key",
                "Cancel",
            ];
            match Select::with_theme(&theme)
                .with_prompt("  What would you like to change?")
                .items(&actions)
                .default(0)
                .interact_opt()
            {
                Ok(Some(0)) => (false, true,  false), // model only
                Ok(Some(1)) => (true,  false, false), // key only
                Ok(Some(2)) => (true,  true,  false), // both
                _           => { println!("  {}\n", "Cancelled.".dimmed()); return; }
            }
        } else {
            let ep = saved_endpoint.as_deref().unwrap_or("(default)");
            println!(
                "\n  {} Currently:  {}  ·  model {}  ·  endpoint {}\n",
                "·".bright_cyan(),
                provider.bright_cyan().bold(),
                saved_model.bright_white(),
                ep.dimmed(),
            );
            let actions = [
                "Change model",
                "Change endpoint",
                "Change model and endpoint",
                "Cancel",
            ];
            match Select::with_theme(&theme)
                .with_prompt("  What would you like to change?")
                .items(&actions)
                .default(0)
                .interact_opt()
            {
                Ok(Some(0)) => (false, true,  false), // model only
                Ok(Some(1)) => (false, false, true),  // endpoint only
                Ok(Some(2)) => (false, true,  true),  // both
                _           => { println!("  {}\n", "Cancelled.".dimmed()); return; }
            }
        }
    } else {
        // First time — collect everything
        (is_cloud, true, is_local)
    };

    // ── Step 4: API key prompt (cloud, when needed) ───────────────────────────
    let api_key: Option<String> = if is_cloud && need_key {
        let env_var = match provider {
            "openai"    => "OPENAI_API_KEY",
            "anthropic" => "ANTHROPIC_API_KEY",
            _           => "GEMINI_API_KEY",
        };
        let hint = match effective_key {
            Some(k) => format!("  New API key  [current: {}  — press Enter to keep]", mask_key(k)),
            None    => format!("  API key  (or set {} env var)", env_var),
        };
        let key: String = Input::with_theme(&theme)
            .with_prompt(&hint)
            .allow_empty(true)
            .interact_text()
            .unwrap_or_default();
        if key.is_empty() {
            if saved_key.is_some() {
                saved_key.clone() // preserve what was in the file
            } else if env_key.is_some() {
                None // key lives in env var — don't write it to the file
            } else {
                println!("  {} No API key provided — skipped.\n", "!".bright_yellow());
                return;
            }
        } else {
            Some(key)
        }
    } else {
        saved_key.clone() // carry forward unchanged
    };

    // ── Step 5: model selection (when needed) ─────────────────────────────────
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
        _ => &[], // vllm / ollama: free-text below
    };

    let selected_model: String = if need_model {
        if !model_menu.is_empty() {
            // Pre-select the currently active model if it appears in the list.
            let pre = model_menu
                .iter()
                .position(|(_, id)| *id == saved_model.as_str())
                .unwrap_or(match provider {
                    "openai"    => 1, // gpt-4o-mini
                    "anthropic" => 1, // claude-sonnet-4-6
                    _           => 0,
                });
            let labels: Vec<&str> = model_menu.iter().map(|(l, _)| *l).collect();
            let mi = match Select::with_theme(&theme)
                .with_prompt("  Model")
                .items(&labels)
                .default(pre)
                .interact_opt()
            {
                Ok(Some(i)) => i,
                _ => { println!("  {}\n", "Cancelled.".dimmed()); return; }
            };
            let (_, model_id) = model_menu[mi];
            if model_id.is_empty() {
                // "Custom…"
                Input::with_theme(&theme)
                    .with_prompt("  Model name")
                    .interact_text()
                    .unwrap_or_default()
            } else {
                model_id.to_string()
            }
        } else {
            // Local provider — free-text, pre-filled with current value
            let default_val = if saved_model.is_empty() {
                match provider {
                    "vllm"   => "meta-llama/Meta-Llama-3.1-8B-Instruct",
                    "ollama" => "llama3.1",
                    _        => "",
                }.to_string()
            } else {
                saved_model.clone()
            };
            Input::with_theme(&theme)
                .with_prompt("  Model name")
                .default(default_val)
                .interact_text()
                .unwrap_or_else(|_| saved_model.clone())
        }
    } else {
        saved_model.clone() // carry forward unchanged
    };

    // ── Step 6: endpoint prompt (local providers, when needed) ────────────────
    let endpoint: Option<String> = if is_local && need_endpoint {
        let (prompt_label, fallback) = match provider {
            "vllm"   => ("  vLLM API base URL", "http://localhost:8000/v1"),
            "ollama" => ("  Ollama base URL",    "http://localhost:11434"),
            _        => ("  Endpoint",           ""),
        };
        let default_ep = saved_endpoint.clone().unwrap_or_else(|| fallback.to_string());
        let ep: String = Input::with_theme(&theme)
            .with_prompt(prompt_label)
            .default(default_ep)
            .interact_text()
            .unwrap_or_else(|_| fallback.to_string());
        Some(ep)
    } else {
        saved_endpoint.clone() // carry forward unchanged
    };

    // ── Step 7: write ~/.structure-d/config.yaml ──────────────────────────────
    let config_dir = dirs::home_dir().unwrap_or_default().join(".structure-d");
    let _ = std::fs::create_dir_all(&config_dir);
    let config_path = config_dir.join("config.yaml");

    let provider_block = match provider {
        "openai" => {
            let key_line = api_key.as_ref()
                .map(|k| format!("    api_key: \"{}\"\n", k))
                .unwrap_or_default();
            format!("  openai:\n{}    model: \"{}\"\n", key_line, selected_model)
        }
        "anthropic" => {
            let key_line = api_key.as_ref()
                .map(|k| format!("    api_key: \"{}\"\n", k))
                .unwrap_or_default();
            format!("  anthropic:\n{}    model: \"{}\"\n", key_line, selected_model)
        }
        "gemini" => {
            let key_line = api_key.as_ref()
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
            "\n  {} Saved → {}\n  {} Provider: {}   Model: {}\n",
            "✓".bright_green().bold(),
            config_path.display().to_string().dimmed(),
            "·".dimmed(),
            provider.bright_cyan().bold(),
            selected_model.bright_cyan().bold(),
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
fn pick_and_run_upload(rl: &mut DefaultEditor) {
    println!("\n  {} Opening file picker…\n", "↑".bright_cyan());

    let file_path = match open_file_dialog() {
        Some(p) => p,
        None => {
            println!("  {}\n", "No file selected.".dimmed());
            return;
        }
    };

    let Some(schema) = prompt_builtin_schema_interactive(rl) else {
        return;
    };

    let Some(fmt) = prompt_output_format_interactive(rl) else {
        return;
    };

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

fn pick_and_run_batch(rl: &mut DefaultEditor) {
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

    let Some(schema) = prompt_builtin_schema_interactive(rl) else {
        return;
    };

    let Some(fmt) = prompt_output_format_interactive(rl) else {
        return;
    };

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

enum DispatchResult {
    /// Keep the REPL running as normal.
    Continue,
    /// Exit the REPL.
    Exit,
    /// Config was written — reload settings and redisplay the status panel.
    Reload,
}

fn dispatch(input: &str, settings: &crate::config::Settings, rl: &mut DefaultEditor) -> DispatchResult {
    let mut parts = input.splitn(2, ' ');
    let cmd = parts.next().unwrap_or("").to_lowercase();
    let rest = parts.next().unwrap_or("").trim();

    match cmd.as_str() {
        "exit" | "quit" | "q" => {
            println!("{}", "Goodbye!".bright_cyan());
            return DispatchResult::Exit;
        }
        "help" | "?" => print_help(),
        "clear" => {
            print!("\x1b[2J\x1b[H");
            print_banner();
        }
        "version" => {
            println!(
                "{} {}\n  {} {}",
                "Structure-D".bold(),
                format!("v{}", env!("CARGO_PKG_VERSION")).bright_cyan().bold(),
                "build".dimmed(),
                env!("GIT_DESCRIBE").dimmed(),
            );
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
        "upload" | "u" => pick_and_run_upload(rl),
        "configure" | "config set" => {
            configure_provider();
            return DispatchResult::Reload;
        }
        "extract" => {
            if rest.is_empty() {
                pick_and_run_upload(rl);
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
                pick_and_run_batch(rl);
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
    DispatchResult::Continue
}

// ── Public entry point ────────────────────────────────────────────────────────

pub fn run_interactive() -> Result<()> {
    let mut settings = crate::config::Settings::load(None).unwrap_or_default();

    print_banner();
    print_init();
    print_ready(&settings);
    print_welcome();
    print_running_exe_line();

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
                match dispatch(&line, &settings, &mut rl) {
                    DispatchResult::Exit => break,
                    DispatchResult::Reload => {
                        // Re-read the config file and redisplay the status panel
                        // so the new provider/model/key is reflected immediately.
                        settings = crate::config::Settings::load(None).unwrap_or_default();
                        println!();
                        print_ready(&settings);
                    }
                    DispatchResult::Continue => {}
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
