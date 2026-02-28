use anyhow::{bail, Result};
use serde_json::Value;
use std::path::Path;

/// Built-in schema definitions as JSON Schema objects.
/// Each schema is a JSON Schema that the LLM output will be validated against.

pub const SCHEMA_NAMES: &[&str] = &[
    "generic",
    "key_value",
    "table",
    "entity",
    "classification",
    "summary",
    "form",
    "document_structure",
];

pub fn list_schemas() -> Vec<(&'static str, &'static str)> {
    vec![
        ("generic", "General-purpose key/value extraction"),
        ("key_value", "Extract explicit key-value pairs from text"),
        ("table", "Extract tabular data into rows and columns"),
        ("entity", "Named entity recognition (people, orgs, locations, dates)"),
        ("classification", "Classify document into predefined categories"),
        ("summary", "Summarise document with title and bullet points"),
        ("form", "Extract structured form fields and values"),
        ("document_structure", "Extract document hierarchy: sections, headings, content"),
    ]
}

/// Returns a JSON Schema Value for the given built-in schema name,
/// or loads from a file path if `name` points to an existing file.
pub fn resolve_schema(name: &str) -> Result<Value> {
    // Check if it's a file path
    let path = Path::new(name);
    if path.exists() {
        let content = std::fs::read_to_string(path)?;
        let schema: Value = serde_json::from_str(&content)?;
        return Ok(schema);
    }

    match name {
        "generic" => Ok(serde_json::json!({
            "type": "object",
            "description": "Generic structured extraction result",
            "properties": {
                "fields": {
                    "type": "object",
                    "description": "Extracted key-value fields",
                    "additionalProperties": { "type": "string" }
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the document"
                }
            },
            "required": ["fields"]
        })),

        "key_value" => Ok(serde_json::json!({
            "type": "object",
            "description": "Explicit key-value pairs extracted from document",
            "properties": {
                "pairs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": { "type": "string" },
                            "value": { "type": "string" },
                            "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
                        },
                        "required": ["key", "value"]
                    }
                }
            },
            "required": ["pairs"]
        })),

        "table" => Ok(serde_json::json!({
            "type": "object",
            "description": "Tabular data extracted from document",
            "properties": {
                "headers": {
                    "type": "array",
                    "items": { "type": "string" }
                },
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": { "type": "string" }
                    }
                },
                "caption": { "type": "string" }
            },
            "required": ["headers", "rows"]
        })),

        "entity" => Ok(serde_json::json!({
            "type": "object",
            "description": "Named entities extracted from document",
            "properties": {
                "persons": { "type": "array", "items": { "type": "string" } },
                "organizations": { "type": "array", "items": { "type": "string" } },
                "locations": { "type": "array", "items": { "type": "string" } },
                "dates": { "type": "array", "items": { "type": "string" } },
                "amounts": { "type": "array", "items": { "type": "string" } },
                "other": { "type": "array", "items": { "type": "string" } }
            },
            "required": ["persons", "organizations", "locations", "dates"]
        })),

        "classification" => Ok(serde_json::json!({
            "type": "object",
            "description": "Document classification result",
            "properties": {
                "label": { "type": "string", "description": "Primary category label" },
                "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
                "secondary_labels": {
                    "type": "array",
                    "items": { "type": "string" }
                },
                "reasoning": { "type": "string" }
            },
            "required": ["label", "confidence"]
        })),

        "summary" => Ok(serde_json::json!({
            "type": "object",
            "description": "Document summary",
            "properties": {
                "title": { "type": "string" },
                "summary": { "type": "string", "description": "1-3 sentence summary" },
                "key_points": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Main bullet points"
                },
                "word_count_estimate": { "type": "integer" }
            },
            "required": ["summary", "key_points"]
        })),

        "form" => Ok(serde_json::json!({
            "type": "object",
            "description": "Form fields extracted from document",
            "properties": {
                "form_type": { "type": "string" },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_name": { "type": "string" },
                            "field_value": { "type": "string" },
                            "field_type": {
                                "type": "string",
                                "enum": ["text", "number", "date", "checkbox", "signature", "other"]
                            }
                        },
                        "required": ["field_name", "field_value"]
                    }
                }
            },
            "required": ["fields"]
        })),

        "document_structure" => Ok(serde_json::json!({
            "type": "object",
            "description": "Document hierarchical structure",
            "properties": {
                "title": { "type": "string" },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": { "type": "string" },
                            "level": { "type": "integer", "minimum": 1, "maximum": 6 },
                            "content": { "type": "string" },
                            "subsections": {
                                "type": "array",
                                "items": { "$ref": "#/properties/sections/items" }
                            }
                        },
                        "required": ["heading", "level", "content"]
                    }
                }
            },
            "required": ["sections"]
        })),

        other => bail!("Unknown schema '{}'. Use one of: {}", other, SCHEMA_NAMES.join(", ")),
    }
}
