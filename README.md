# Structure-D

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.0-informational)](https://github.com/jagguvarma15/Structure-D/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/jagguvarma15/Structure-D/blob/main/LICENSE)
[![Tests](https://img.shields.io/badge/tests-110%20passed-brightgreen?logo=pytest)](https://github.com/jagguvarma15/Structure-D/actions)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-black)](https://github.com/astral-sh/ruff)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/latest/)
[![Built with Rust](https://img.shields.io/badge/CLI-Rust-orange?logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/inference-vLLM-blueviolet)](https://github.com/vllm-project/vllm)

**Built for vLLM. Adaptable to any LLM provider.**

Structure-D is an open-source document extraction framework designed from the ground up for **high-throughput structured inference with [vLLM](https://github.com/vllm-project/vllm)**. It exploits vLLM's `guided_json` constrained decoding to guarantee that every output matches your Pydantic schema — no post-processing, no reformatting, no surprises.

When vLLM is not available (prototyping, cloud-only environments, testing), the same pipeline runs unchanged against **OpenAI, Anthropic, Gemini, or Ollama** — with zero code changes.

Structure-D is **format-focused** (PDF, images, HTML, DOCX, Office, email, text) and **schema-driven** (Pydantic models defining what you want to extract). Results are written to JSONL, CSV, Markdown, or databases. It can be used as:

- A **Python library** (async pipeline API)
- A **FastAPI service** (HTTP API)
- A **Rust CLI** (`structure-d`) for high-throughput batch jobs

---

## Quick Start

### Install (library + CLI + common extras)

```bash
git clone https://github.com/jagguvarma15/Structure-D.git
cd Structure-D
make install          # builds Rust CLI and installs Python package with core extras
```

This creates a `.venv` in the project root and installs `structure-d[ingestion,api,llm]`.

### Run tests

All tests are pure Python and do **not** require external services by default:

```bash
source .venv/bin/activate
pytest tests/ -v
```

You can use markers for larger suites later:

```bash
pytest tests/ -m "not slow and not integration"
pytest tests/ -m "integration"
```

---

## Why vLLM?

vLLM is Structure-D's **primary and recommended inference engine** for production workloads. Here is why the design centres on it:

| Feature | vLLM advantage |
|---------|---------------|
| **Guided decoding** (`guided_json`) | Constrains token sampling directly to your JSON schema — the model physically cannot produce invalid JSON |
| **Throughput** | PagedAttention + continuous batching: hundreds of concurrent requests on a single GPU |
| **Batch processing** | `run_many()` saturates the vLLM server; documents are processed in parallel without rate limits |
| **Model routing** | Structure-D's `ModelRouter` picks the smallest registered model that fits the task, reducing cost and latency |
| **Self-hosted** | No per-token cloud billing; flat GPU cost regardless of volume |

Cloud providers (OpenAI, Anthropic, Gemini, Ollama) are **fully supported as drop-in alternatives**. They use prompt-based structured output (function calling or `response_format`) instead of guided decoding, so validation and retry logic still applies. They are ideal for:

- Early prototyping before standing up a vLLM server
- Tasks where a frontier model's reasoning outweighs throughput concerns
- Fallback when the local vLLM server is unavailable

Set `fallback_provider: "anthropic"` (or any other provider) in `configs/default.yaml` to get automatic failover with zero code changes.

---

## Core Concepts

- **Ingestion**: Format-specific parsers (`structure_d/ingestion/`) turn files into `ParsedDocument`. Supported: PDF (PyMuPDF, pdfplumber, OCR), DOCX (text + tables + headings + metadata), HTML (structure, tables, meta tags, links), images (Tesseract OCR), XLSX, PPTX, email, audio transcripts, plain text, Markdown, CSV.
- **Preprocessing**: Normalisation + chunking (`structure_d/preprocessing/`) turn text into `TextChunk`s.
- **Inference**: vLLM (`guided_json`) is the primary engine; OpenAI, Anthropic, Gemini, and Ollama are optional alternatives. All providers share the same `BaseLLMProvider` interface in `structure_d/inference/providers.py`.
- **Validation & Retry**: Schema validation + refined re-prompts (`structure_d/validation/`) ensure outputs conform to Pydantic schemas.
- **Storage**: Writers for **JSONL**, **CSV**, **Markdown (`.md`)**, and databases (`structure_d/storage/`). Cloud destinations (Snowflake, BigQuery, Redshift, MySQL) available as optional extras.
- **Indexing & RAG**: `DocumentReader`, `VectorStoreIndex`, `SummaryIndex`, `QueryEngine`, and `RAGPipeline` for retrieval and QA.

Entry points:

- Library: `structure_d.pipeline.Pipeline`
- API: `structure_d.api.app.create_app`
- CLI (Rust): `structure-d` (see `cli/` and `Makefile`)

---

## Using the Python Pipeline

### Basic extraction

**With vLLM (recommended for production):**

```python
import asyncio
from pathlib import Path

from structure_d.pipeline import Pipeline
from structure_d.inference.providers import VLLMProvider
from structure_d.schemas.generic import KeyValueExtraction


async def main() -> None:
    # VLLMProvider is the default — no argument needed if vllm is configured
    pipeline = Pipeline(
        schema_cls=KeyValueExtraction,
        provider=VLLMProvider(),   # points to http://localhost:8000/v1 by default
    )

    # Format is auto-detected — works for PDF, DOCX, HTML, images, etc.
    results = await pipeline.run(
        Path("docs/sample.pdf"),
        save_format="jsonl",        # "jsonl" | "csv" | "markdown"
    )
    for r in results:
        if r.is_valid:
            print(r.structured_output)


if __name__ == "__main__":
    asyncio.run(main())
```

**With a cloud provider (prototyping / no GPU):**

```python
from structure_d.inference.providers import AnthropicProvider

pipeline = Pipeline(
    schema_cls=KeyValueExtraction,
    provider=AnthropicProvider(),  # reads ANTHROPIC_API_KEY from env
)
```

### RAG indexing and querying

```python
import asyncio
from pathlib import Path

from structure_d.pipeline import Pipeline
from structure_d.retrieval.vector_store import ChromaVectorStore


async def main() -> None:
    pipeline = Pipeline(
        schema_cls=None,      # schema not needed just for RAG
        enable_rag=True,
        vector_store=ChromaVectorStore(),
    )

    index = await pipeline.build_index(Path("docs/report.pdf"), index_type="vector")
    engine = index.as_query_engine(provider=pipeline.provider)
    answer = await engine.query("What is the total amount?")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
```

### Provider reference

| Provider | Class | Structured output mechanism | Best for |
|----------|-------|-----------------------------|----------|
| **vLLM** _(default)_ | `VLLMProvider` | `guided_json` constrained decoding | Production, high-throughput, self-hosted |
| OpenAI | `OpenAIProvider` | `response_format: json_schema` | Cloud, frontier models (GPT-4o) |
| Anthropic | `AnthropicProvider` | Tool-use structured output | Cloud, frontier models (Claude) |
| Gemini | `GeminiProvider` | Structured generation | Cloud, Google ecosystem |
| Ollama | `OllamaProvider` | JSON mode | Local dev, no GPU server needed |

All providers are configured under `inference.provider` in `configs/default.yaml`.  
Switch at runtime: `SD_INFERENCE__PROVIDER__PROVIDER=openai`.

---

## Running the API

Install API extras (if you did `make install` this is already included):

```bash
source .venv/bin/activate
pip install -e ".[api]"
```

Run the FastAPI app (for local development):

```bash
uvicorn structure_d.api.app:create_app --factory --host 0.0.0.0 --port 8080
```

Key endpoints:

- `GET /api/v1/health` – health check
- `GET /api/v1/models` – list configured models
- `GET /api/v1/schemas` – list built-in schemas
- `GET /api/v1/formats` – list supported formats and extensions
- `POST /api/v1/extract` – upload a document and get structured results

---

## Running the Rust CLI

The Rust CLI is built and installed by `make install`. Once installed:

```bash
structure-d --help
```

Key commands:

```bash
# Interactive terminal (schema picker + format picker)
structure-d

# Extract one or more files
structure-d extract report.pdf --schema key_value --output-format jsonl
structure-d extract invoice.docx --schema form --output-format md --output output/invoice.md

# Batch-extract a directory
structure-d batch ./documents/ --schema entity --output-format csv
structure-d batch ./docs/ --schema document_structure --output-format md

# Informational
structure-d schemas           # list built-in extraction schemas
structure-d formats           # list supported input formats
structure-d models            # list configured models
structure-d config            # show active configuration
structure-d status --check    # ping the configured LLM provider
```

Output format choices for `--output-format`:

| Flag value | Output |
|------------|--------|
| `jsonl` | One JSON object per result (default) |
| `csv` | One row per result, `structured_output` flattened to columns |
| `md` | Human-readable Markdown with metadata table + fenced JSON per result |

---

## Testing & Development

- All Python code targets **Python 3.10+** with type hints and `pydantic` v2.
- Async I/O is used for all external calls (HTTP, I/O, DB, vector stores).
- Logging uses `structlog`; no `print()` in library code.

Common dev commands:

```bash
make install-dev     # install dev extras (pytest, ruff, mypy, etc.)
make test            # run full test suite
make lint            # ruff lint
make fmt             # ruff format
make clean           # remove build artifacts and caches
```

The current test suite includes:

- Configuration and settings loading
- Core schemas and schema registry
- Normalisation and chunking
- Ingestion manager and parsers (plain text, HTML, email, DOCX)
- Batch processing and retry logic
- Storage writers (JSONL, CSV, Markdown)
- Documents, Nodes, indexing helpers
- FastAPI endpoints
- End-to-end `Pipeline` tests with a fake, in-memory LLM provider

---

## Output formats

Structure-D produces structured output in three file formats, all selectable via `save_format` in Python or `--output-format` in the CLI:

| Format | When to use |
|--------|-------------|
| **JSONL** (default) | Pipelines, downstream processing, log ingestion. Each record is a fully-indented JSON object separated by a blank line. |
| **CSV** | Spreadsheets, BI tools. `structured_output` fields are flattened to dot-notation columns. |
| **Markdown** | Human review, docs-as-data, Git diffs. Each result renders as `## Result N` with a metadata table and fenced JSON block. |

All three can also be written manually via `JSONLWriter`, `CSVWriter`, or `MarkdownWriter` from `structure_d.storage`.

## Documentation

Full documentation is available at [jagguvarma15.github.io/Structure-D](https://jagguvarma15.github.io/Structure-D/).

