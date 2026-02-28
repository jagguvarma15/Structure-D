use anyhow::{Context, Result};
use mailparse::MailHeaderMap;
use std::path::Path;

use super::{DocumentFormat, ParsedDocument};

pub fn parse(path: &Path) -> Result<ParsedDocument> {
    let raw = std::fs::read(path)
        .with_context(|| format!("Failed to read email file: {}", path.display()))?;

    let mail = mailparse::parse_mail(&raw)
        .with_context(|| format!("Failed to parse email: {}", path.display()))?;

    let mut parts: Vec<String> = Vec::new();

    // Extract headers
    if let Some(subject) = mail.headers.get_first_value("Subject") {
        parts.push(format!("Subject: {}", subject));
    }
    if let Some(from) = mail.headers.get_first_value("From") {
        parts.push(format!("From: {}", from));
    }
    if let Some(to) = mail.headers.get_first_value("To") {
        parts.push(format!("To: {}", to));
    }
    if let Some(date) = mail.headers.get_first_value("Date") {
        parts.push(format!("Date: {}", date));
    }
    parts.push(String::new());

    // Extract body (prefer text/plain, fall back to text/html)
    extract_body(&mail, &mut parts);

    let content = parts.join("\n");

    let mut doc = ParsedDocument::new(content, path, DocumentFormat::Email);

    // Store subject in metadata
    if let Some(subject) = mail.headers.get_first_value("Subject") {
        doc.metadata.insert("subject".into(), serde_json::json!(subject));
    }

    Ok(doc)
}

fn extract_body(mail: &mailparse::ParsedMail, parts: &mut Vec<String>) {
    let ctype = &mail.ctype.mimetype;

    if ctype == "text/plain" {
        if let Ok(body) = mail.get_body() {
            parts.push(body);
        }
    } else if ctype == "text/html" {
        if let Ok(body) = mail.get_body() {
            let text = crate::ingestion::html::extract_text_from_html(&body);
            parts.push(text);
        }
    } else if ctype.starts_with("multipart/") {
        // Prefer text/plain over text/html
        let mut found_plain = false;
        for sub in &mail.subparts {
            if sub.ctype.mimetype == "text/plain" {
                extract_body(sub, parts);
                found_plain = true;
                break;
            }
        }
        if !found_plain {
            for sub in &mail.subparts {
                if sub.ctype.mimetype == "text/html" {
                    extract_body(sub, parts);
                    break;
                }
            }
        }
    }
}
