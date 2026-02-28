use anyhow::{Context, Result};
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use super::ExtractionResult;

pub struct JSONLWriter {
    pub output_path: String,
}

impl JSONLWriter {
    pub fn new(output_path: &str) -> Self {
        Self { output_path: output_path.to_string() }
    }

    pub fn write(&self, results: &[ExtractionResult]) -> Result<()> {
        // Ensure parent directory exists
        let path = Path::new(&self.output_path);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create output directory: {}", parent.display()))?;
        }

        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.output_path)
            .with_context(|| format!("Failed to open JSONL file: {}", self.output_path))?;

        for result in results {
            let line = serde_json::to_string(result)?;
            writeln!(file, "{}", line)?;
        }

        Ok(())
    }
}

pub fn save_as_jsonl(results: &[ExtractionResult], path: &str) -> Result<()> {
    JSONLWriter::new(path).write(results)
}

/// Write to stdout as JSONL (one result per line)
pub fn print_as_jsonl(results: &[ExtractionResult]) -> Result<()> {
    let stdout = std::io::stdout();
    let mut handle = stdout.lock();
    for result in results {
        let line = serde_json::to_string(result)?;
        writeln!(handle, "{}", line)?;
    }
    Ok(())
}
