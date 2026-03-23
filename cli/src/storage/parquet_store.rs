use std::fs::File;
use std::path::Path;
use std::sync::Arc;

use anyhow::{Context, Result};
use arrow_array::{ArrayRef, RecordBatch, StringArray};
use arrow_schema::{DataType, Field, Schema};
use parquet::arrow::arrow_writer::ArrowWriter;
use parquet::basic::{Compression, ZstdLevel};
use parquet::file::properties::WriterProperties;

use super::tabular;
use super::ExtractionResult;

pub fn save_as_parquet(results: &[ExtractionResult], path: &str) -> Result<()> {
    let p = Path::new(path);
    if let Some(parent) = p.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create output directory: {}", parent.display()))?;
    }

    let (headers, rows) = tabular::tabular_headers_and_rows(results);

    let fields: Vec<Field> = headers
        .iter()
        .map(|h| Field::new(h.as_str(), DataType::Utf8, true))
        .collect();
    let schema = Arc::new(Schema::new(fields));

    let num_cols = headers.len();
    let num_rows = rows.len();

    let mut columns: Vec<ArrayRef> = Vec::with_capacity(num_cols);
    for col_idx in 0..num_cols {
        let col: Vec<String> = (0..num_rows)
            .map(|ri| rows[ri].get(col_idx).cloned().unwrap_or_default())
            .collect();
        columns.push(Arc::new(StringArray::from(col)));
    }

    let batch = RecordBatch::try_new(schema.clone(), columns).context("build Arrow RecordBatch")?;

    let file = File::create(path).with_context(|| format!("Failed to create Parquet file: {}", path))?;
    let props = WriterProperties::builder()
        .set_compression(Compression::ZSTD(ZstdLevel::default()))
        .build();
    let mut writer = ArrowWriter::try_new(file, schema, Some(props))
        .context("create Parquet ArrowWriter")?;
    writer.write(&batch).context("write Parquet batch")?;
    writer.close().context("close Parquet writer")?;
    Ok(())
}
