"""Prometheus metrics for pipeline monitoring."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

import structlog

logger = structlog.get_logger(__name__)

# We lazily import prometheus_client so it's optional.
_PROM_AVAILABLE = False
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server

    _PROM_AVAILABLE = True
except ImportError:
    pass


class MetricsCollector:
    """
    Collect and expose pipeline metrics via Prometheus.

    Requires: ``pip install structure-d[monitoring]``
    """

    def __init__(self, namespace: str = "structure_d") -> None:
        self.namespace = namespace
        self._started = False

        if _PROM_AVAILABLE:
            self.docs_ingested = Counter(
                f"{namespace}_docs_ingested_total",
                "Total documents ingested",
            )
            self.chunks_processed = Counter(
                f"{namespace}_chunks_processed_total",
                "Total chunks processed",
            )
            self.inference_latency = Histogram(
                f"{namespace}_inference_latency_seconds",
                "Inference latency in seconds",
                buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
            )
            self.validation_failures = Counter(
                f"{namespace}_validation_failures_total",
                "Validation failures",
            )
            self.tokens_used = Counter(
                f"{namespace}_tokens_used_total",
                "Total tokens consumed",
                ["type"],  # prompt / completion
            )
            self.active_requests = Gauge(
                f"{namespace}_active_requests",
                "Currently active inference requests",
            )
        else:
            logger.info(
                "prometheus_not_available",
                msg="Install prometheus_client for metrics",
            )

    def start_server(self, port: int = 9090) -> None:
        """Start the Prometheus metrics HTTP server."""
        if not _PROM_AVAILABLE:
            return
        if self._started:
            return
        start_http_server(port)
        self._started = True
        logger.info("prometheus_server_started", port=port)

    # ── Recording helpers ─────────────────────────────────────────────────────

    def record_ingestion(self, count: int = 1) -> None:
        if _PROM_AVAILABLE:
            self.docs_ingested.inc(count)

    def record_chunks(self, count: int) -> None:
        if _PROM_AVAILABLE:
            self.chunks_processed.inc(count)

    def record_inference_latency(self, seconds: float) -> None:
        if _PROM_AVAILABLE:
            self.inference_latency.observe(seconds)

    def record_validation_failure(self, count: int = 1) -> None:
        if _PROM_AVAILABLE:
            self.validation_failures.inc(count)

    def record_tokens(self, prompt: int = 0, completion: int = 0) -> None:
        if _PROM_AVAILABLE:
            self.tokens_used.labels(type="prompt").inc(prompt)
            self.tokens_used.labels(type="completion").inc(completion)

    @contextmanager
    def track_request(self) -> Generator[None, None, None]:
        """Context manager that tracks active requests and latency."""
        if _PROM_AVAILABLE:
            self.active_requests.inc()
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - t0
            if _PROM_AVAILABLE:
                self.active_requests.dec()
                self.inference_latency.observe(elapsed)
