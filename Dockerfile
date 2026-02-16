# ──────────────────────────────────────────────────────────────
# Structure-D – Multi-stage Docker image
# ──────────────────────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for PDF / OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[all]"

# Copy source code
COPY . .
RUN pip install --no-cache-dir -e .

# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpq5 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages and app from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create output and log directories
RUN mkdir -p /app/output /app/logs /app/data

ENV SD_CONFIG_PATH=/app/configs/default.yaml
EXPOSE 8080

CMD ["structure-d", "serve", "--host", "0.0.0.0", "--port", "8080"]
