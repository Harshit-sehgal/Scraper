from argparse import ArgumentTypeError
from datetime import UTC, datetime

import pytest

from scripts.run_load_test import LoadTestConfig, RequestSample, build_result, parse_headers, percentile


def _config(
    *,
    url: str = "http://localhost:8000/health",
    concurrency: int = 2,
    requests: int = 5,
    timeout_seconds: float = 1.0,
    expected_status: int = 200,
    p95_threshold_ms: float = 250.0,
    max_failures: int = 0,
    headers: dict[str, str] | None = None,
) -> LoadTestConfig:
    return LoadTestConfig(
        url=url,
        concurrency=concurrency,
        requests=requests,
        timeout_seconds=timeout_seconds,
        expected_status=expected_status,
        p95_threshold_ms=p95_threshold_ms,
        max_failures=max_failures,
        headers=headers or {},
    )


def test_percentile_uses_nearest_rank_for_small_sets():
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0.50) == 20.0
    assert percentile(values, 0.95) == 40.0
    assert percentile([10.0], 0.99) == 10.0
    assert percentile([], 0.95) == 0.0


def test_build_result_passes_when_failures_and_latency_are_within_thresholds():
    samples = [
        RequestSample(latency_ms=10.0, status_code=200),
        RequestSample(latency_ms=20.0, status_code=200),
        RequestSample(latency_ms=30.0, status_code=200),
        RequestSample(latency_ms=40.0, status_code=200),
        RequestSample(latency_ms=50.0, status_code=200),
    ]

    result = build_result(_config(), samples, 0.5, generated_at=datetime(2026, 6, 24, tzinfo=UTC))

    assert result.passed is True
    assert result.failure_reason == ""
    assert result.successful == 5
    assert result.failures == 0
    assert result.p95_latency_ms == 50.0
    assert result.requests_per_second == 10.0
    assert result.to_dict()["generated_at"] == "2026-06-24T00:00:00+00:00"


def test_build_result_fails_when_any_request_fails_by_default():
    samples = [
        RequestSample(latency_ms=10.0, status_code=200),
        RequestSample(latency_ms=11.0, status_code=500),
    ]

    result = build_result(_config(requests=2), samples, 0.2)

    assert result.passed is False
    assert result.failure_reason == "failures_exceeded:1>0"


def test_build_result_fails_when_p95_exceeds_threshold():
    samples = [
        RequestSample(latency_ms=10.0, status_code=200),
        RequestSample(latency_ms=500.0, status_code=200),
    ]

    result = build_result(_config(requests=2, p95_threshold_ms=100.0), samples, 0.2)

    assert result.passed is False
    assert result.failure_reason == "p95_exceeded:500.00>100.00"


def test_parse_headers_requires_name_value_separator():
    assert parse_headers(["X-API-Key: token", "Accept: application/json"]) == {
        "Accept": "application/json",
        "X-API-Key": "token",
    }

    with pytest.raises(ArgumentTypeError):
        parse_headers(["broken"])
