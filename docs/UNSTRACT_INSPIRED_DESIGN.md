# Structure-D Enhancement Plan: Inspired by Unstract

## Overview

This document outlines enhancements to Structure-D inspired by [Unstract](https://docs.unstract.com/unstract/), a no-code LLM platform for document processing. While Structure-D remains a code-first framework (not no-code), we can adopt Unstract's architectural patterns, connector ecosystem, and workflow capabilities.

## Key Unstract Features to Adopt

### 1. **Enhanced Connector Ecosystem** ✅ Partially Implemented

**Current State:**
- ✅ Local filesystem
- ✅ AWS S3
- ✅ HTTP/HTTPS
- ❌ Google Cloud Storage (GCS)
- ❌ Azure Blob Storage
- ❌ Google Drive
- ❌ Dropbox
- ❌ Box
- ❌ SFTP

**Implementation Plan:**
- Create `structure_d/ingestion/connectors/` module
- Implement `BaseConnector` interface (already exists)
- Add connectors: `GCSConnector`, `AzureConnector`, `GoogleDriveConnector`, `DropboxConnector`, `BoxConnector`, `SFTPConnector`
- Use async I/O and credential management via environment variables or config

### 2. **Destination Writers** ✅ Partially Implemented

**Current State:**
- ✅ JSONL files
- ✅ CSV files
- ✅ PostgreSQL (with PGVector)
- ❌ Snowflake
- ❌ Google BigQuery
- ❌ Amazon Redshift
- ❌ MySQL/MariaDB
- ❌ Microsoft SQL Server
- ❌ Oracle

**Implementation Plan:**
- Create `structure_d/storage/destinations/` module
- Implement `BaseDestination` interface
- Add writers: `SnowflakeWriter`, `BigQueryWriter`, `RedshiftWriter`, `MySQLWriter`, `MSSQLWriter`, `OracleWriter`
- Support batch inserts, schema mapping, and error handling

### 3. **ETL Pipeline Framework** ❌ Not Implemented

**Unstract Feature:** Scheduled batch processing from sources to destinations

**Implementation Plan:**
- Create `structure_d/etl/` module
- Define `ETLPipeline` class:
  ```python
  class ETLPipeline:
      source: BaseConnector
      destination: BaseDestination
      pipeline: Pipeline  # existing Pipeline class
      schedule: str | None  # cron expression
      filters: dict[str, Any]  # file filters
  ```
- Add workflow definitions in YAML:
  ```yaml
  etl_pipelines:
    - name: "daily_invoice_processing"
      source:
        type: "s3"
        bucket: "invoices"
        prefix: "raw/"
      destination:
        type: "snowflake"
        table: "invoices"
      pipeline:
        schema: "KeyValueExtraction"
        model: "llama-3.1-8b"
      schedule: "0 2 * * *"  # daily at 2 AM
      filters:
        extensions: [".pdf", ".png"]
        max_size_mb: 50
  ```
- Add CLI command: `structure-d etl run <pipeline-name>`
- Add scheduler integration (APScheduler or Celery Beat)

### 4. **Prompt Template Management** ❌ Not Implemented

**Unstract Feature:** Prompt Studio for managing and testing prompts

**Implementation Plan:**
- Create `structure_d/prompts/` module
- Define `PromptTemplate` class:
  ```python
  class PromptTemplate:
      name: str
      version: str
      system_prompt: str
      user_prompt_template: str  # Jinja2 template
      examples: list[dict]
      metadata: dict[str, Any]
  ```
- Store templates in `configs/prompts/` directory (YAML files)
- Add CLI commands:
  - `structure-d prompt list`
  - `structure-d prompt test <name> --file <path>`
  - `structure-d prompt create <name>`
- Support versioning and A/B testing

### 5. **Multi-LLM Provider Support** ✅ Partially Implemented

**Current State:**
- ✅ vLLM (OpenAI-compatible API)
- ❌ OpenAI (direct)
- ❌ Anthropic Claude
- ❌ Google Gemini
- ❌ Azure OpenAI
- ❌ Ollama (local models)

**Implementation Plan:**
- Create `structure_d/inference/providers/` module
- Implement `BaseLLMProvider` interface:
  ```python
  class BaseLLMProvider:
      async def generate(
          self,
          prompt: str,
          schema: Type[BaseModel],
          **kwargs
      ) -> BaseModel
  ```
- Add providers: `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`, `AzureOpenAIProvider`, `OllamaProvider`
- Update `VLLMClient` to be a provider implementation
- Add provider selection in config:
  ```yaml
  inference:
    provider: "vllm"  # vllm | openai | anthropic | gemini | ollama
    vllm: {...}
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
  ```

### 6. **Human-in-the-Loop (HITL)** ❌ Not Implemented

**Unstract Feature:** Review and approval workflows for low-confidence extractions

**Implementation Plan:**
- Create `structure_d/hitl/` module
- Add confidence scoring to extraction results
- Implement review queue:
  ```python
  class ReviewQueue:
      async def add_review(
          self,
          extraction: ExtractionResult,
          confidence: float,
          threshold: float = 0.7
      )
      async def get_pending_reviews() -> list[ReviewItem]
      async def approve(review_id: str, corrections: dict)
      async def reject(review_id: str, reason: str)
  ```
- Add API endpoints:
  - `GET /api/v1/reviews` - list pending reviews
  - `POST /api/v1/reviews/{id}/approve` - approve with corrections
  - `POST /api/v1/reviews/{id}/reject` - reject
- Store reviews in database with audit trail

### 7. **Analytics & Monitoring** ✅ Partially Implemented

**Current State:**
- ✅ Prometheus metrics (latency, throughput)
- ✅ Structured logging
- ❌ Extraction success rates
- ❌ Field fill rates
- ❌ Cost tracking per model/provider
- ❌ Quality metrics (precision, recall)

**Implementation Plan:**
- Extend `MetricsCollector`:
  ```python
  class MetricsCollector:
      def record_extraction_success(
          self,
          schema: str,
          fields_extracted: int,
          fields_total: int
      )
      def record_cost(
          self,
          provider: str,
          model: str,
          tokens_input: int,
          tokens_output: int,
          cost_usd: float
      )
  ```
- Add analytics dashboard data:
  - `GET /api/v1/analytics/success-rates`
  - `GET /api/v1/analytics/field-fill-rates`
  - `GET /api/v1/analytics/costs`
- Create `structure_d/analytics/` module for aggregation queries

### 8. **Workflow Definitions** ❌ Not Implemented

**Unstract Feature:** YAML-based workflow definitions for complex pipelines

**Implementation Plan:**
- Create `structure_d/workflows/` module
- Define workflow schema:
  ```yaml
  workflows:
    - name: "document_classification_pipeline"
      steps:
        - type: "ingest"
          connector: "s3"
          prefix: "documents/"
        - type: "classify"
          schema: "ClassificationResult"
          model: "llama-3.1-8b"
        - type: "route"
          # route to different extractors based on classification
          routes:
            invoice: "invoice_extraction"
            resume: "resume_extraction"
        - type: "store"
          destination: "postgresql"
          table: "extracted_data"
      retry:
        max_attempts: 3
        backoff: "exponential"
  ```
- Implement `WorkflowEngine` to execute workflows
- Support conditional routing, parallel steps, error handling

### 9. **API Authentication & Security** ❌ Not Implemented

**Current State:**
- ❌ No authentication
- ❌ No API keys
- ❌ No rate limiting

**Implementation Plan:**
- Add API key authentication:
  ```python
  class APIKeyAuth:
      async def verify_key(self, key: str) -> bool
  ```
- Store API keys in database or environment
- Add rate limiting middleware (slowapi)
- Add OAuth2 support (optional, for enterprise)

### 10. **Enhanced Monitoring Dashboard** ❌ Not Implemented

**Unstract Feature:** Web UI for monitoring (optional, can be CLI-based)

**Implementation Plan:**
- Create CLI-based dashboard:
  - `structure-d dashboard` - interactive terminal dashboard
  - Show real-time metrics, extraction queue, recent jobs
- Optional: Add simple web dashboard (FastAPI + HTML/JS)
- Display:
  - Extraction success rates
  - Field fill rates by schema
  - Cost per document
  - Processing queue status
  - Recent errors

## Implementation Priority

### Phase 1: Core Infrastructure (High Priority)
1. ✅ Enhanced Connectors (GCS, Azure, SFTP)
2. ✅ Destination Writers (Snowflake, BigQuery, MySQL)
3. ✅ Multi-LLM Provider Support
4. ✅ Prompt Template Management

### Phase 2: Workflow & Automation (Medium Priority)
5. ✅ ETL Pipeline Framework
6. ✅ Workflow Definitions
7. ✅ Analytics & Enhanced Monitoring

### Phase 3: Enterprise Features (Lower Priority)
8. ✅ Human-in-the-Loop
9. ✅ API Authentication
10. ✅ Monitoring Dashboard

## Architecture Decisions

### 1. **Code-First vs No-Code**
- **Decision:** Remain code-first (Python API + CLI)
- **Rationale:** Structure-D targets developers, not business users
- **Trade-off:** More flexible, but requires coding knowledge

### 2. **Provider Abstraction**
- **Decision:** Abstract LLM providers behind `BaseLLMProvider`
- **Rationale:** Allows switching providers without changing pipeline code
- **Implementation:** Factory pattern with provider registry

### 3. **Workflow Engine**
- **Decision:** YAML-based workflow definitions with Python execution
- **Rationale:** Declarative workflows are easier to version and test
- **Implementation:** Parse YAML → build DAG → execute with async tasks

### 4. **Storage Abstraction**
- **Decision:** Abstract destinations behind `BaseDestination`
- **Rationale:** Consistent interface for all storage backends
- **Implementation:** Similar to connector pattern

## References

- [Unstract Documentation](https://docs.unstract.com/unstract/)
- [Unstract GitHub](https://github.com/Zipstack/unstract)
- [Unstract Connectors](https://docs.unstract.com/unstract/connectors/)
- [Unstract Adapters](https://docs.unstract.com/unstract/adapters/)
