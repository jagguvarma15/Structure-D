//! Build script — embeds live git version info into the binary so every build
//! carries its own precise identity without needing a runtime `git` call.
//!
//! Two env vars are made available via `env!` / `option_env!`:
//!
//! | Variable              | Example value            | Meaning                          |
//! |-----------------------|--------------------------|----------------------------------|
//! | `GIT_DESCRIBE`        | `v0.2.0-3-gabcdef`       | tag + commits-since + short SHA  |
//! | `GIT_SHA`             | `abcdef1`                | short commit SHA                 |
//!
//! If git is unavailable (e.g. in a vendor/offline build), both vars fall back
//! to `"unknown"` so the build never breaks.

fn main() {
    // Re-run whenever HEAD or any branch ref changes (new commit, checkout, …)
    println!("cargo:rerun-if-changed=.git/HEAD");
    println!("cargo:rerun-if-changed=.git/refs");

    // git describe --tags --always --dirty=+modified
    //   "v0.2.0"             → clean tagged release
    //   "v0.2.0-3-gabcdef"   → 3 commits beyond v0.2.0
    //   "v0.2.0-3-gabcdef+modified" → uncommitted changes on top
    let describe = run_git(&["describe", "--tags", "--always", "--dirty=+modified"])
        .unwrap_or_else(|| "unknown".into());

    let sha = run_git(&["rev-parse", "--short", "HEAD"])
        .unwrap_or_else(|| "unknown".into());

    println!("cargo:rustc-env=GIT_DESCRIBE={}", describe);
    println!("cargo:rustc-env=GIT_SHA={}", sha);
}

fn run_git(args: &[&str]) -> Option<String> {
    let out = std::process::Command::new("git")
        .args(args)
        .output()
        .ok()?;
    if out.status.success() {
        Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
    } else {
        None
    }
}
