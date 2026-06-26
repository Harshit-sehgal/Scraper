#!/usr/bin/env python3
"""Multi-endpoint load profile runner for DataForge ops readiness.

P1-OPS-LOAD-ALERT-001: extends the load test coverage beyond /health
to include /ready and /healthz so operators can verify multiple
critical paths survive concurrent load.

This is a thin wrapper over ``scripts/run_load_test.py`` logic — it
reuses the same worker/percentile/build_result primitives but runs
them against a profile of endpoints instead of a single URL.

Usage::

    python3 scripts/run_load_profile.py --base-url http://localhost:8000
    python3 scripts/run_load_profile.py --base-url http://localhost:8000 --json-file artifacts/load_test/latest_profile.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_PROFILE: tuple[tuple[str, int], ...] = (
    ("/health", 200),
    ("/ready", 200),
)
DEFAULT_P95_THRESHOLD_MS = 250.0
DEFAULT_CONCURRENCY = 10
DEFAULT_REQUESTS_PER_ENDPOINT = 50
DEFAULT_MAX_FAILURES = 0


@dataclass(frozen=True)
class EndpointResult:
    endpoint: str
    expected_status: int
    requested: int
    successful: int
    failures: int
    min_latency_ms: float
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    requests_per_second: float
    total_elapsed_seconds: float
    passed: bool
    failure_reason: str


@dataclass(frozen=True)
class LoadProfileResult:
    generated_at: str
    base_url: str
    concurrency: int
    p95_threshold_ms: float
    max_failures: int
    endpoints: list[dict[str, Any]]
    total_requested: int
    total_successful: int
    total_failures: int
    passed: bool
    failure_reason: str


def percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    if quantile <= 0:
        return sorted_values[0]
    if quantile >= 1:
        return sorted_values[-1]
    index = max(0, min(len(sorted_values) - 1, math.ceil(len(sorted_values) * quantile) - 1))
    return sorted_values[index]


async def _load_endpoint(
    base_url: str,
    path: str,
    expected_status: int,
    concurrency: int,
    requests: int,
    timeout_seconds: float,
    p95_threshold_ms: float,
    max_failures: int,
) -> EndpointResult:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    samples: list[Any] = []

    async def single_request(client: httpx.AsyncClient) -> tuple[float, int, str]:
        start = time.perf_counter()
        try:
            resp = await client.get(url, timeout=timeout_seconds)
            elapsed_ms = (time.perf_counter() - start) * 1000
            return elapsed_ms, resp.status_code, ""
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return elapsed_ms, -1, exc.__class__.__name__

    start_total = time.perf_counter()
    async with httpx.AsyncClient(follow_redirects=False) as client:
        sem = asyncio.Semaphore(concurrency)

        async def bounded_request() -> tuple[float, int, str]:
            async with sem:
                return await single_request(client)

        tasks = [asyncio.create_task(bounded_request()) for _ in range(requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                samples.append((0.0, -1, r.__class__.__name__))
            else:
                samples.append(r)

    elapsed_total = time.perf_counter() - start_total

    latencies = sorted(lat for lat, status, err in samples if status == expected_status and not err)
    successful = len(latencies)
    failures = len(samples) - successful
    elapsed = max(elapsed_total, 0.000001)

    avg = sum(latencies) / successful if latencies else 0.0
    p95 = percentile(latencies, 0.95)

    failure_reason = ""
    if not latencies:
        failure_reason = "all_requests_failed"
    elif failures > max_failures:
        failure_reason = f"failures_exceeded:{failures}>{max_failures}"
    elif p95 > p95_threshold_ms:
        failure_reason = f"p95_exceeded:{p95:.2f}>{p95_threshold_ms:.2f}"

    return EndpointResult(
        endpoint=path,
        expected_status=expected_status,
        requested=requests,
        successful=successful,
        failures=failures,
        min_latency_ms=round(latencies[0], 2) if latencies else 0.0,
        average_latency_ms=round(avg, 2),
        p50_latency_ms=round(percentile(latencies, 0.50), 2),
        p95_latency_ms=round(p95, 2),
        p99_latency_ms=round(percentile(latencies, 0.99), 2),
        max_latency_ms=round(latencies[-1], 2) if latencies else 0.0,
        requests_per_second=round(successful / elapsed, 2),
        total_elapsed_seconds=round(elapsed_total, 6),
        passed=not failure_reason,
        failure_reason=failure_reason,
    )


async def run_load_profile(
    base_url: str,
    *,
    profile: tuple[tuple[str, int], ...] = DEFAULT_PROFILE,
    concurrency: int = DEFAULT_CONCURRENCY,
    requests_per_endpoint: int = DEFAULT_REQUESTS_PER_ENDPOINT,
    timeout_seconds: float = 5.0,
    p95_threshold_ms: float = DEFAULT_P95_THRESHOLD_MS,
    max_failures: int = DEFAULT_MAX_FAILURES,
) -> LoadProfileResult:
    endpoint_results: list[EndpointResult] = []
    for path, expected_status in profile:
        result = await _load_endpoint(
            base_url,
            path,
            expected_status,
            concurrency=concurrency,
            requests=requests_per_endpoint,
            timeout_seconds=timeout_seconds,
            p95_threshold_ms=p95_threshold_ms,
            max_failures=max_failures,
        )
        endpoint_results.append(result)

    total_requested = sum(r.requested for r in endpoint_results)
    total_successful = sum(r.successful for r in endpoint_results)
    total_failures = sum(r.failures for r in endpoint_results)

    failed_endpoints = [r for r in endpoint_results if not r.passed]
    failure_reason = ""
    if failed_endpoints:
        failure_reason = "; ".join(f"{r.endpoint}: {r.failure_reason}" for r in failed_endpoints)

    return LoadProfileResult(
        generated_at=datetime.now(UTC).isoformat(),
        base_url=base_url,
        concurrency=concurrency,
        p95_threshold_ms=p95_threshold_ms,
        max_failures=max_failures,
        endpoints=[asdict(r) for r in endpoint_results],
        total_requested=total_requested,
        total_successful=total_successful,
        total_failures=total_failures,
        passed=not failure_reason,
        failure_reason=failure_reason,
    )


def format_human(result: LoadProfileResult) -> str:
    lines = [
        "=" * 70,
        f"DataForge Load Profile: {result.base_url}",
        f"Concurrency: {result.concurrency} | p95 threshold: {result.p95_threshold_ms}ms",
        "=" * 70,
    ]
    for ep in result.endpoints:
        status = "[OK]" if ep["passed"] else f"[FAIL: {ep['failure_reason']}]"
        lines.append(f"  {ep['endpoint']}: {ep['successful']}/{ep['requested']} OK, p95={ep['p95_latency_ms']:.1f}ms  {status}")
    lines.append("")
    lines.append(f"Total: {result.total_successful}/{result.total_requested} passed")
    gate = "[OK] Profile gate passed." if result.passed else f"[FAIL] Profile gate failed: {result.failure_reason}"
    lines.append(f"  {gate}")
    return "\n".join(lines)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DataForge multi-endpoint load profile")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL (e.g. http://localhost:8000)")
    parser.add_argument("--concurrency", type=positive_int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--requests", type=positive_int, default=DEFAULT_REQUESTS_PER_ENDPOINT, help="Requests per endpoint")
    parser.add_argument("--timeout", type=positive_float, default=5.0)
    parser.add_argument("--p95-threshold-ms", type=positive_float, default=DEFAULT_P95_THRESHOLD_MS)
    parser.add_argument("--max-failures", type=int, default=DEFAULT_MAX_FAILURES)
    parser.add_argument("--json", action="store_true", help="Print only JSON to stdout")
    parser.add_argument("--json-file", type=Path, help="Write JSON result to this path")

    # F-SCRIPT-001 host context guard
    parser.add_argument("--allow-remote-host", action="store_true")

    args = parser.parse_args(argv)

    parsed = urlparse(args.base_url)
    host_is_local = parsed.hostname in (None, "localhost", "127.0.0.1", "::1")
    env_allow = os.environ.get("DATAFORGE_DRILL_ALLOW_REMOTE") == "1"
    if not host_is_local and not (args.allow_remote_host or env_allow):
        msg = (
            f"Refusing to run load profile against non-localhost host "
            f"{parsed.hostname!r}. Re-run with --allow-remote-host "
            "or set DATAFORGE_DRILL_ALLOW_REMOTE=1. F-SCRIPT-001."
        )
        if args.json:
            print(json.dumps({"status": "refused", "reason": msg}))
        else:
            print(f"[ERROR] {msg}", file=sys.stderr)
        return 4

    result = asyncio.run(
        run_load_profile(
            args.base_url,
            concurrency=args.concurrency,
            requests_per_endpoint=args.requests,
            timeout_seconds=args.timeout,
            p95_threshold_ms=args.p95_threshold_ms,
            max_failures=args.max_failures,
        )
    )

    payload = json.dumps(asdict(result), indent=2, sort_keys=True)
    if args.json_file:
        args.json_file.parent.mkdir(parents=True, exist_ok=True)
        args.json_file.write_text(payload + "\n", encoding="utf-8")
    if args.json:
        print(payload)
    else:
        print(format_human(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
