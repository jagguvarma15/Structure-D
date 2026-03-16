# Structure-D

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.1.0-informational)](https://github.com/jagguvarma15/Structure-D/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/jagguvarma15/Structure-D/blob/main/LICENSE)
[![Tests](https://img.shields.io/badge/tests-110%20passed-brightgreen?logo=pytest)](https://github.com/jagguvarma15/Structure-D/actions)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-black)](https://github.com/astral-sh/ruff)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/latest/)
[![Built with Rust](https://img.shields.io/badge/CLI-Rust-orange?logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/inference-vLLM-blueviolet)](https://github.com/vllm-project/vllm)

An open-source framework to ingest unstructured documents and reliably produce validated, schema-constrained structured data (JSON/CSV/DB), optimized for high-throughput inference with vLLM structured outputs.

Structure-D is **format-focused** (PDF, images, HTML, Office, email, text) and **schema-driven** (Pydantic models defining what you want to extract). It can be used as:

- A **Python library** (async pipeline API)
- A **FastAPI service** (HTTP API)
- A **Rust CLI** (`structure-d`) for high-throughput batch jobs

---

## Quick Start

### Install (library + CLI + common extras)

```bash
git clone https://github.com/JagadeshVarma/Structure-D.git
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

## Core Concepts

- **Ingestion**: Format-specific parsers (`structure_d/ingestion/`) turn files into `ParsedDocument`.
- **Preprocessing**: Normalisation + chunking (`structure_d/preprocessing/`) turn text into `TextChunk`s.
- **Inference**: Multi-provider LLM abstraction (`structure_d/inference/providers.py`) turns chunks into structured data.
- **Validation & Retry**: Schema validation + refined re-prompts (`structure_d/validation/`) ensure outputs conform to Pydantic schemas.
- **Storage**: Writers for JSONL, CSV, and databases (`structure_d/storage/`).
- **Indexing & RAG**: `DocumentReader`, `VectorStoreIndex`, `SummaryIndex`, `QueryEngine`, and `RAGPipeline` for retrieval and QA.

Entry points:

- Library: `structure_d.pipeline.Pipeline`
- API: `structure_d.api.app.create_app`
- CLI (Rust): `structure-d` (see `cli/` and `Makefile`)

---

## Using the Python Pipeline

### Basic extraction

```python
import asyncio
from pathlib import Path

from structure_d.pipeline import Pipeline
from structure_d.inference.providers import OpenAIProvider
from structure_d.schemas.generic import KeyValueExtraction


async def main() -> None:
    pipeline = Pipeline(
        schema_cls=KeyValueExtraction,
        provider=OpenAIProvider(),  # or VLLMProvider(), AnthropicProvider(), etc.
    )

    results = await pipeline.run(Path("docs/sample.pdf"))
    for r in results:
        print(r.structured_output)


if __name__ == "__main__":
    asyncio.run(main())
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

Typical commands (subject to change as the CLI evolves):

- `structure-d extract` – one-off extraction from local files
- `structure-d formats` – list supported formats
- `structure-d models` – list configured models

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
- Ingestion manager and parsers (text, HTML, email)
- Batch processing and retry logic
- Storage writers (JSONL, CSV)
- Documents, Nodes, indexing helpers
- FastAPI endpoints
- End-to-end `Pipeline` tests with a fake, in-memory LLM provider

---

## Documentation

For more details, see:

- `docs/IMPLEMENTATION_SUMMARY.md` – implementation status and indexing overview
- `docs/UNSTRACT_INSPIRED_DESIGN.md` – design plan inspired by Unstract

