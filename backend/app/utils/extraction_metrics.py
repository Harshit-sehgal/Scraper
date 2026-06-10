"""Extraction quality metrics and performance tracking.

Tracks extraction quality, performance, and accuracy metrics
for monitoring and improvement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionMetrics:
    """Metrics for a single extraction operation."""

    job_id: str
    url: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    success: bool = False
    error: str | None = None

    # Quality metrics
    fields_extracted: int = 0
    fields_expected: int = 0
    data_completeness: float = 0.0
    confidence_score: float = 0.0

    # Performance metrics
    extraction_time_ms: float = 0.0
    network_time_ms: float = 0.0
    ai_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Data quality
    empty_fields: int = 0
    malformed_data: int = 0
    duplicates_detected: int = 0

    # Anti-bot metrics
    anti_bot_score: float = 0.0
    stealth_success: bool = True
    retries_needed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "url": self.url,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "success": self.success,
            "error": self.error,
            "fields_extracted": self.fields_extracted,
            "fields_expected": self.fields_expected,
            "data_completeness": self.data_completeness,
            "confidence_score": self.confidence_score,
            "extraction_time_ms": self.extraction_time_ms,
            "network_time_ms": self.network_time_ms,
            "ai_time_ms": self.ai_time_ms,
            "total_time_ms": self.total_time_ms,
            "empty_fields": self.empty_fields,
            "malformed_data": self.malformed_data,
            "duplicates_detected": self.duplicates_detected,
            "anti_bot_score": self.anti_bot_score,
            "stealth_success": self.stealth_success,
            "retries_needed": self.retries_needed,
        }


class ExtractionQualityTracker:
    """Track extraction quality metrics across jobs."""

    def __init__(self):
        self._metrics: list[ExtractionMetrics] = []
        self._start_times: dict[str, float] = {}

    def start_extraction(self, job_id: str, url: str) -> ExtractionMetrics:
        """Start tracking an extraction."""
        metrics = ExtractionMetrics(job_id=job_id, url=url)
        self._start_times[job_id] = time.time()
        return metrics

    def end_extraction(self, metrics: ExtractionMetrics) -> ExtractionMetrics:
        """End tracking an extraction and calculate metrics."""
        metrics.end_time = time.time()
        metrics.total_time_ms = (metrics.end_time - metrics.start_time) * 1000

        # Calculate data completeness
        if metrics.fields_expected > 0:
            metrics.data_completeness = metrics.fields_extracted / metrics.fields_expected

        self._metrics.append(metrics)
        return metrics

    def get_job_metrics(self, job_id: str) -> ExtractionMetrics | None:
        """Get metrics for a specific job."""
        for m in reversed(self._metrics):
            if m.job_id == job_id:
                return m
        return None

    def get_all_metrics(self) -> list[ExtractionMetrics]:
        """Get all metrics."""
        return self._metrics.copy()

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        if not self._metrics:
            return {"total_extractions": 0}

        total = len(self._metrics)
        successful = sum(1 for m in self._metrics if m.success)
        failed = total - successful

        avg_time = sum(m.total_time_ms for m in self._metrics) / total if total > 0 else 0
        avg_completeness = sum(m.data_completeness for m in self._metrics) / total if total > 0 else 0
        avg_confidence = sum(m.confidence_score for m in self._metrics) / total if total > 0 else 0

        return {
            "total_extractions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "avg_extraction_time_ms": avg_time,
            "avg_data_completeness": avg_completeness,
            "avg_confidence_score": avg_confidence,
            "total_empty_fields": sum(m.empty_fields for m in self._metrics),
            "total_malformed_data": sum(m.malformed_data for m in self._metrics),
            "total_duplicates_detected": sum(m.duplicates_detected for m in self._metrics),
        }

    def get_domain_metrics(self, domain: str) -> dict[str, Any]:
        """Get metrics filtered by domain."""
        domain_metrics = [m for m in self._metrics if domain in m.url]
        if not domain_metrics:
            return {"domain": domain, "total_extractions": 0}

        total = len(domain_metrics)
        successful = sum(1 for m in domain_metrics if m.success)

        return {
            "domain": domain,
            "total_extractions": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "avg_extraction_time_ms": sum(m.total_time_ms for m in domain_metrics) / total if total > 0 else 0,
            "avg_data_completeness": sum(m.data_completeness for m in domain_metrics) / total if total > 0 else 0,
        }

    def get_performance_report(self) -> dict[str, Any]:
        """Generate performance report."""
        summary = self.get_summary()

        # Calculate percentiles
        times = sorted(m.total_time_ms for m in self._metrics)
        if times:
            p50 = times[len(times) // 2]
            p95 = times[int(len(times) * 0.95)]
            p99 = times[int(len(times) * 0.99)]
        else:
            p50 = p95 = p99 = 0

        return {
            **summary,
            "performance": {
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "min_ms": min(times) if times else 0,
                "max_ms": max(times) if times else 0,
            },
        }


# Global tracker instance
quality_tracker = ExtractionQualityTracker()


def get_quality_tracker() -> ExtractionQualityTracker:
    """Get the global quality tracker."""
    return quality_tracker
