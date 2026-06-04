"""Shared Metrics Collector — holds runtime metric state that is read by the
/metrics endpoint and written by middleware, workers, and other subsystems.

This module is deliberately separate from main.py to avoid circular imports
when worker_queue.py or other modules need to record metrics.
"""

import threading

_MAX_METRIC_SAMPLES = 1000

# Ring buffer for API request durations (seconds)
_request_latencies: list[float] = []
_request_latencies_lock = threading.Lock()

# Worker failure counters: task_type -> count
_worker_failures: dict[str, int] = {}
_worker_failures_lock = threading.Lock()

# Backend health check durations (seconds) — ring buffer
_health_check_latencies: list[float] = []
_health_check_latencies_lock = threading.Lock()

# Generic error counters: type -> count (e.g. database, network, scraper)
_errors_total: dict[str, int] = {}
_errors_total_lock = threading.Lock()

# LLM call counters
_llm_calls_total: int = 0
_llm_calls_total_lock = threading.Lock()

# Total request counter
_requests_total: int = 0
_requests_total_lock = threading.Lock()


def record_request_latency(duration_seconds: float) -> None:
    """Record an API request duration for metrics export."""
    global _request_latencies, _requests_total
    with _request_latencies_lock:
        _request_latencies.append(duration_seconds)
        if len(_request_latencies) > _MAX_METRIC_SAMPLES:
            _request_latencies = _request_latencies[-_MAX_METRIC_SAMPLES:]
    with _requests_total_lock:
        _requests_total += 1


def record_worker_failure(task_type: str) -> None:
    """Increment the worker failure counter for a task type.

    Called by worker_queue.py when a task enters dead_letter state.
    """
    with _worker_failures_lock:
        _worker_failures[task_type] = _worker_failures.get(task_type, 0) + 1


def record_health_check_latency(duration_seconds: float) -> None:
    """Record a backend health check duration."""
    global _health_check_latencies
    with _health_check_latencies_lock:
        _health_check_latencies.append(duration_seconds)
        if len(_health_check_latencies) > _MAX_METRIC_SAMPLES:
            _health_check_latencies = _health_check_latencies[-_MAX_METRIC_SAMPLES:]


def record_error(error_type: str) -> None:
    """Increment cumulative error counts by type."""
    with _errors_total_lock:
        _errors_total[error_type] = _errors_total.get(error_type, 0) + 1


def record_llm_call() -> None:
    """Increment cumulative LLM call count."""
    global _llm_calls_total
    with _llm_calls_total_lock:
        _llm_calls_total += 1


def get_request_latencies() -> list[float]:
    with _request_latencies_lock:
        return list(_request_latencies)


def get_worker_failures() -> dict[str, int]:
    with _worker_failures_lock:
        return dict(_worker_failures)


def get_health_check_latencies() -> list[float]:
    with _health_check_latencies_lock:
        return list(_health_check_latencies)


def get_errors() -> dict[str, int]:
    with _errors_total_lock:
        return dict(_errors_total)


def get_llm_calls() -> int:
    with _llm_calls_total_lock:
        return _llm_calls_total


def get_requests_total() -> int:
    with _requests_total_lock:
        return _requests_total


def reset_for_testing() -> None:
    """Reset all counters and buffers (for test isolation)."""
    global _llm_calls_total, _requests_total
    with _request_latencies_lock:
        _request_latencies.clear()
    with _worker_failures_lock:
        _worker_failures.clear()
    with _health_check_latencies_lock:
        _health_check_latencies.clear()
    with _errors_total_lock:
        _errors_total.clear()
    with _llm_calls_total_lock:
        _llm_calls_total = 0
    with _requests_total_lock:
        _requests_total = 0
