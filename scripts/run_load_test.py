#!/usr/bin/env python3
"""Bounded HTTP load test utility for DataForge ops drills.

The script intentionally keeps scope narrow: it sends concurrent GET
requests to one URL, computes latency percentiles, and fails closed when
the configured failure or p95 threshold is exceeded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:8000/health"
DEFAULT_P95_THRESHOLD_MS = 250.0


@dataclass(frozen=True)
class LoadTestConfig:
    url: str
    concurrency: int
    requests: int
    timeout_seconds: float
    expected_status: int
    p95_threshold_ms: float
    max_failures: int
    headers: dict[str, str]


@dataclass(frozen=True)
class RequestSample:
    latency_ms: float
    status_code: int
    error: str = ""


@dataclass(frozen=True)
class LoadTestResult:
    generated_at: str
    target_url: str
    concurrency: int
    requested: int
    completed: int
    successful: int
    failures: int
    expected_status: int
    total_elapsed_seconds: float
    requests_per_second: float
    min_latency_ms: float
    average_latency_ms: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    p95_threshold_ms: float
    max_failures: int
    passed: bool
    failure_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def percentile(sorted_values: list[float], quantile: float) -> float:
    """Return the nearest-rank percentile for an already sorted list."""
    if not sorted_values:
        return 0.0
    if quantile <= 0:
        return sorted_values[0]
    if quantile >= 1:
        return sorted_values[-1]
    index = max(0, min(len(sorted_values) - 1, math.ceil(len(sorted_values) * quantile) - 1))
    return sorted_values[index]


def build_result(
    config: LoadTestConfig,
    samples: list[RequestSample],
    total_elapsed_seconds: float,
    *,
    generated_at: datetime | None = None,
) -> LoadTestResult:
    latencies = sorted(
        sample.latency_ms for sample in samples if sample.status_code == config.expected_status and not sample.error
    )
    successful = len(latencies)
    failures = len(samples) - successful
    elapsed = max(total_elapsed_seconds, 0.000001)

    if latencies:
        average = sum(latencies) / successful
        p95 = percentile(latencies, 0.95)
        min_latency = latencies[0]
        max_latency = latencies[-1]
    else:
        average = 0.0
        p95 = 0.0
        min_latency = 0.0
        max_latency = 0.0

    failure_reason = ""
    if not latencies:
        failure_reason = "all_requests_failed"
    elif failures > config.max_failures:
        failure_reason = f"failures_exceeded:{failures}>{config.max_failures}"
    elif p95 > config.p95_threshold_ms:
        failure_reason = f"p95_exceeded:{p95:.2f}>{config.p95_threshold_ms:.2f}"

    return LoadTestResult(
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        target_url=config.url,
        concurrency=config.concurrency,
        requested=config.requests,
        completed=len(samples),
        successful=successful,
        failures=failures,
        expected_status=config.expected_status,
        total_elapsed_seconds=round(total_elapsed_seconds, 6),
        requests_per_second=round(successful / elapsed, 2),
        min_latency_ms=round(min_latency, 2),
        average_latency_ms=round(average, 2),
        p50_latency_ms=round(percentile(latencies, 0.50), 2),
        p90_latency_ms=round(percentile(latencies, 0.90), 2),
        p95_latency_ms=round(p95, 2),
        p99_latency_ms=round(percentile(latencies, 0.99), 2),
        max_latency_ms=round(max_latency, 2),
        p95_threshold_ms=round(config.p95_threshold_ms, 2),
        max_failures=config.max_failures,
        passed=not failure_reason,
        failure_reason=failure_reason,
    )


async def send_request(client: httpx.AsyncClient, config: LoadTestConfig) -> RequestSample:
    start = time.perf_counter()
    try:
        response = await client.get(config.url, headers=config.headers, timeout=config.timeout_seconds)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return RequestSample(latency_ms=elapsed_ms, status_code=-1, error=exc.__class__.__name__)

    elapsed_ms = (time.perf_counter() - start) * 1000
    return RequestSample(latency_ms=elapsed_ms, status_code=response.status_code)


async def worker(config: LoadTestConfig, queue: asyncio.Queue[None], samples: list[RequestSample]) -> None:
    async with httpx.AsyncClient(follow_redirects=False) as client:
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            try:
                samples.append(await send_request(client, config))
            finally:
                queue.task_done()


async def run_load_test(config: LoadTestConfig) -> LoadTestResult:
    queue: asyncio.Queue[None] = asyncio.Queue()
    for _ in range(config.requests):
        queue.put_nowait(None)

    samples: list[RequestSample] = []
    start = time.perf_counter()
    workers = [asyncio.create_task(worker(config, queue, samples)) for _ in range(config.concurrency)]
    await queue.join()

    for task in workers:
        task.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    total_elapsed_seconds = time.perf_counter() - start
    return build_result(config, samples, total_elapsed_seconds)


def format_human(result: LoadTestResult) -> str:
    gate_status = "[OK] Load test validation threshold passed successfully."
    if not result.passed:
        gate_status = f"[FAIL] Load test validation failed: {result.failure_reason}"

    lines = [
        "=" * 70,
        f"Starting DataForge Load Test: {result.target_url}",
        f"Concurrency: {result.concurrency} workers | Total requests: {result.requested}",
        "=" * 70,
        "",
        "Performance metrics:",
        f"  Total time elapsed:  {result.total_elapsed_seconds:.3f} seconds",
        f"  Successful requests: {result.successful}/{result.completed} ({result.failures} failures)",
        f"  Requests/sec (RPS):  {result.requests_per_second:.2f}",
        f"  Minimum latency:     {result.min_latency_ms:.2f} ms",
        f"  Average latency:     {result.average_latency_ms:.2f} ms",
        f"  p50 (median):        {result.p50_latency_ms:.2f} ms",
        f"  p90:                 {result.p90_latency_ms:.2f} ms",
        f"  p95:                 {result.p95_latency_ms:.2f} ms",
        f"  p99:                 {result.p99_latency_ms:.2f} ms",
        f"  Maximum latency:     {result.max_latency_ms:.2f} ms",
        "",
        "Validation Gate Status:",
        f"  {gate_status}",
    ]
    return "\n".join(lines)


def parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in values:
        name, separator, value = raw.partition(":")
        if not separator or not name.strip():
            raise argparse.ArgumentTypeError(f"header must use 'Name: value' format: {raw!r}")
        headers[name.strip()] = value.strip()
    return headers


def positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return value


def positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DataForge bounded HTTP load test utility")
    parser.add_argument("--url", default=DEFAULT_URL, help="Target URL to load test")
    parser.add_argument("--concurrency", type=positive_int, default=30, help="Number of concurrent workers")
    parser.add_argument("--requests", type=positive_int, default=300, help="Total requests to dispatch")
    parser.add_argument("--timeout", type=positive_float, default=5.0, help="Per-request timeout in seconds")
    parser.add_argument("--expected-status", type=positive_int, default=200, help="HTTP status code counted as success")
    parser.add_argument(
        "--p95-threshold-ms", type=positive_float, default=DEFAULT_P95_THRESHOLD_MS, help="Maximum allowed p95 latency"
    )
    parser.add_argument("--max-failures", type=int, default=0, help="Maximum allowed failed responses")
    parser.add_argument("--header", action="append", default=[], help="Extra request header, e.g. 'X-API-Key: value'")
    parser.add_argument("--json", action="store_true", help="Print only JSON to stdout")
    parser.add_argument("--json-file", type=Path, help="Write JSON result to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_failures < 0:
        parser.error("--max-failures must be >= 0")

    config = LoadTestConfig(
        url=args.url,
        concurrency=args.concurrency,
        requests=args.requests,
        timeout_seconds=args.timeout,
        expected_status=args.expected_status,
        p95_threshold_ms=args.p95_threshold_ms,
        max_failures=args.max_failures,
        headers=parse_headers(args.header),
    )

    try:
        result = asyncio.run(run_load_test(config))
    except KeyboardInterrupt:
        print("\nTest interrupted.", file=sys.stderr)
        return 130

    json_payload = json.dumps(result.to_dict(), indent=2, sort_keys=True)
    if args.json_file:
        args.json_file.parent.mkdir(parents=True, exist_ok=True)
        args.json_file.write_text(json_payload + "\n", encoding="utf-8")

    if args.json:
        print(json_payload)
    else:
        print(format_human(result))

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
