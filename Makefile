.PHONY: install install-dev install-vllm install-all build-rust test clean help

# ─── Onboarding ──────────────────────────────────────────────────────────────

## Build the Rust CLI + install Python SDK (start here)
install:
	cargo build --release
	pip install -e ".[ingestion,api,llm]"
	@echo ""
	@echo "Done. Run: ./target/release/structure-d --help"

## Install + dev tools (pytest, ruff, mypy)
install-dev:
	pip install -e ".[ingestion,api,llm,dev]"

## Add self-hosted inference support (vLLM, HuggingFace — requires GPU, large download)
install-vllm:
	pip install -e ".[inference]"

## Install every optional dependency
install-all:
	pip install -e ".[all,dev]"

# ─── Rust CLI (optional, for performance) ────────────────────────────────────

## Build the Rust CLI binary
build-rust:
	cargo build --release
	@echo ""
	@echo "Built: ./target/release/structure-d"

# ─── Dev ─────────────────────────────────────────────────────────────────────

## Run tests
test:
	pytest tests/ -v

## Lint and format check
lint:
	ruff check structure_d/ tests/

## Auto-fix lint issues
fmt:
	ruff format structure_d/ tests/

# ─── Cleanup ─────────────────────────────────────────────────────────────────

## Remove build artifacts
clean:
	rm -rf build dist *.egg-info .pytest_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Structure-D — available targets:"
	@echo ""
	@grep -E '^## ' Makefile | sed 's/^## /  /'
	@echo ""
	@echo "Quick start:"
	@echo "  make install          # install everything needed to use the CLI"
	@echo "  structure-d --help    # see available commands"
	@echo ""

.DEFAULT_GOAL := help
