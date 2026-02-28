use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;
use uuid::Uuid;

// Matches sentence-ending punctuation followed by whitespace and a capital letter or end.
// Cannot use lookbehind in Rust regex, so we capture the whole pattern differently.
static RE_HEADING: OnceLock<Regex> = OnceLock::new();

fn re_heading() -> &'static Regex {
    RE_HEADING.get_or_init(|| {
        Regex::new(r"(?m)^(#{1,6})\s+(.+)$").unwrap()
    })
}

/// Split text into sentences by finding [.!?] followed by whitespace.
/// Since Rust regex doesn't support lookbehind, we do this manually.
fn split_sentences(text: &str) -> Vec<&str> {
    let bytes = text.as_bytes();
    let len = bytes.len();
    let mut boundaries: Vec<usize> = vec![0];

    for i in 0..len {
        let ch = bytes[i] as char;
        if (ch == '.' || ch == '!' || ch == '?') && i + 1 < len {
            // Look ahead for whitespace
            let next = bytes[i + 1] as char;
            if next == ' ' || next == '\n' || next == '\t' {
                boundaries.push(i + 2); // start after punctuation + space
            }
        }
    }

    let mut sentences = Vec::new();
    for i in 0..boundaries.len() {
        let start = boundaries[i];
        let end = if i + 1 < boundaries.len() { boundaries[i + 1] } else { len };
        // Make sure start/end are on valid char boundaries
        let slice = &text[start..end];
        let trimmed = slice.trim();
        if !trimmed.is_empty() {
            sentences.push(&text[start..end]);
        }
    }
    if sentences.is_empty() && !text.trim().is_empty() {
        sentences.push(text);
    }
    sentences
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextChunk {
    pub id: Uuid,
    pub document_id: Uuid,
    pub text: String,
    pub chunk_index: usize,
    pub token_estimate: usize,
}

impl TextChunk {
    fn new(text: String, document_id: Uuid, index: usize) -> Self {
        let token_estimate = estimate_tokens(&text);
        Self {
            id: Uuid::new_v4(),
            document_id,
            text,
            chunk_index: index,
            token_estimate,
        }
    }
}

/// Rough token estimate: ~4 chars per token.
pub fn estimate_tokens(text: &str) -> usize {
    (text.len() + 3) / 4
}

pub struct Chunker {
    pub strategy: String,
    pub max_tokens: usize,
    pub overlap: usize,
}

impl Chunker {
    pub fn new(strategy: &str, max_tokens: usize, overlap: usize) -> Self {
        Self {
            strategy: strategy.to_string(),
            max_tokens,
            overlap,
        }
    }

    pub fn chunk(&self, text: &str, document_id: Uuid) -> Vec<TextChunk> {
        match self.strategy.as_str() {
            "fixed" => self.chunk_fixed(text, document_id),
            "sentence" => self.chunk_sentence(text, document_id),
            "heading" => self.chunk_heading(text, document_id),
            "semantic" | _ => self.chunk_semantic(text, document_id),
        }
    }

    /// Split every max_tokens characters with overlap.
    fn chunk_fixed(&self, text: &str, document_id: Uuid) -> Vec<TextChunk> {
        let chars: Vec<char> = text.chars().collect();
        let step = (self.max_tokens * 4).saturating_sub(self.overlap * 4);
        let window = self.max_tokens * 4;

        if step == 0 || window == 0 {
            return vec![TextChunk::new(text.to_string(), document_id, 0)];
        }

        let mut chunks = Vec::new();
        let mut start = 0usize;

        while start < chars.len() {
            let end = (start + window).min(chars.len());
            let slice: String = chars[start..end].iter().collect();
            chunks.push(TextChunk::new(slice, document_id, chunks.len()));
            if end == chars.len() {
                break;
            }
            start += step;
        }

        chunks
    }

    /// Split on sentence boundaries (.!?) then group into chunks.
    fn chunk_sentence(&self, text: &str, document_id: Uuid) -> Vec<TextChunk> {
        let sentences = split_sentences(text);
        self.group_segments(&sentences, document_id)
    }

    /// Split on Markdown headings, each section becomes a chunk.
    fn chunk_heading(&self, text: &str, document_id: Uuid) -> Vec<TextChunk> {
        let mut sections: Vec<String> = Vec::new();
        let mut current = String::new();

        for line in text.lines() {
            if re_heading().is_match(line) && !current.trim().is_empty() {
                sections.push(current.trim().to_string());
                current = String::new();
            }
            current.push_str(line);
            current.push('\n');
        }
        if !current.trim().is_empty() {
            sections.push(current.trim().to_string());
        }

        if sections.is_empty() {
            // No headings found — fall back to sentence chunking
            return self.chunk_sentence(text, document_id);
        }

        let refs: Vec<&str> = sections.iter().map(|s| s.as_str()).collect();
        self.group_segments(&refs, document_id)
    }

    /// Semantic chunking: heading-aware sentence splitting (default).
    fn chunk_semantic(&self, text: &str, document_id: Uuid) -> Vec<TextChunk> {
        // Split on headings first, then sentence-split within each section
        let mut all_sentences: Vec<String> = Vec::new();
        let mut current_heading = String::new();
        let mut current_section = String::new();

        for line in text.lines() {
            if re_heading().is_match(line) {
                if !current_section.trim().is_empty() {
                    // Sentence-split the current section
                    let with_heading = if current_heading.is_empty() {
                        current_section.trim().to_string()
                    } else {
                        format!("{}\n{}", current_heading, current_section.trim())
                    };
                    for sent in split_sentences(&with_heading) {
                        let s = sent.trim();
                        if !s.is_empty() {
                            all_sentences.push(s.to_string());
                        }
                    }
                }
                current_heading = line.to_string();
                current_section = String::new();
            } else {
                current_section.push_str(line);
                current_section.push('\n');
            }
        }

        // Handle last section
        if !current_section.trim().is_empty() {
            let with_heading = if current_heading.is_empty() {
                current_section.trim().to_string()
            } else {
                format!("{}\n{}", current_heading, current_section.trim())
            };
            for sent in split_sentences(&with_heading) {
                let s = sent.trim();
                if !s.is_empty() {
                    all_sentences.push(s.to_string());
                }
            }
        }

        if all_sentences.is_empty() {
            all_sentences.push(text.to_string());
        }

        let refs: Vec<&str> = all_sentences.iter().map(|s| s.as_str()).collect();
        self.group_segments(&refs, document_id)
    }

    /// Group segments (sentences/sections) into chunks respecting max_tokens with overlap.
    fn group_segments(&self, segments: &[&str], document_id: Uuid) -> Vec<TextChunk> {
        let mut chunks: Vec<TextChunk> = Vec::new();
        let mut current_tokens = 0usize;
        let mut current_segs: Vec<&str> = Vec::new();

        for seg in segments {
            let seg_tokens = estimate_tokens(seg);

            // If adding this segment would exceed max_tokens, flush current chunk
            if current_tokens + seg_tokens > self.max_tokens && !current_segs.is_empty() {
                let text = current_segs.join(" ");
                chunks.push(TextChunk::new(text, document_id, chunks.len()));

                // Keep overlap: retain last few segments
                let overlap_chars = self.overlap * 4;
                let mut overlap_segs: Vec<&str> = Vec::new();
                let mut overlap_len = 0;
                for s in current_segs.iter().rev() {
                    if overlap_len + s.len() > overlap_chars {
                        break;
                    }
                    overlap_segs.push(s);
                    overlap_len += s.len();
                }
                overlap_segs.reverse();
                current_segs = overlap_segs;
                current_tokens = current_segs.iter().map(|s| estimate_tokens(s)).sum();
            }

            current_segs.push(seg);
            current_tokens += seg_tokens;
        }

        // Flush remaining
        if !current_segs.is_empty() {
            let text = current_segs.join(" ");
            if !text.trim().is_empty() {
                chunks.push(TextChunk::new(text, document_id, chunks.len()));
            }
        }

        if chunks.is_empty() {
            // Fallback: single chunk with all text
            let all = segments.join(" ");
            if !all.trim().is_empty() {
                chunks.push(TextChunk::new(all, document_id, 0));
            }
        }

        chunks
    }
}
