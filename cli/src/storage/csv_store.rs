use anyhow::{Context, Result};
use std::path::Path;

use super::tabular;
use super::ExtractionResult;

pub struct CSVWriter {
    pub output_path: String,
}

impl CSVWriter {
    pub fn new(output_path: &str) -> Self {
        Self { output_path: output_path.to_string() }
    }

    pub fn write(&self, results: &[ExtractionResult]) -> Result<()> {
        let path = Path::new(&self.output_path);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create output directory: {}", parent.display()))?;
        }

        let (headers, rows) = tabular::tabular_headers_and_rows(results);

        let mut writer = csv::Writer::from_path(&self.output_path)
            .with_context(|| format!("Failed to create CSV file: {}", self.output_path))?;

        writer.write_record(&headers)?;

        for row in &rows {
            writer.write_record(row)?;
        }

        writer.flush()?;
        Ok(())
    }
}

pub fn save_as_csv(results: &[ExtractionResult], path: &str) -> Result<()> {
    CSVWriter::new(path).write(results)
}
