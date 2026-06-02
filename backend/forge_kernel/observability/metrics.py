"""
Metrics — Prometheus-compatible metrics collector for the kernel.

Provides minimal counter/histogram/timer for core operations.
Full Prometheus integration uses the existing app.metrics_collector.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class KernelMetrics:
    """Lightweight metrics collector for the kernel."""

    def __init__(self):
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, count: int = 1):
        """Increment a counter."""
        self._counters[name] += count

    def record(self, name: str, value: float):
        """Record a value in a histogram."""
        self._histograms[name].append(value)
        # Cap histogram storage to prevent unbounded memory growth
        if len(self._histograms[name]) > 1000:
            self._histograms[name] = self._histograms[name][-500:]

    def timer(self, name: str):
        """Context manager for timing operations."""

        class _Timer:
            def __init__(self, metrics: KernelMetrics, name: str):
                self.metrics = metrics
                self.name = name
                self.start = 0.0

            def __enter__(self):
                self.start = time.monotonic()
                return self

            def __exit__(self, *args: Any):
                duration = (time.monotonic() - self.start) * 1000
                self.metrics.record(self.name, duration)

        return _Timer(self, name)

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all metrics for /metrics endpoints."""
        return {
            "counters": dict(self._counters),
            "histogram_means": {k: (sum(v) / len(v)) if v else 0.0 for k, v in self._histograms.items()},
            "histogram_counts": {k: len(v) for k, v in self._histograms.items()},
        }


_metrics = KernelMetrics()


def get_kernel_metrics() -> KernelMetrics:
    return _metrics
