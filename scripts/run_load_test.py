#!/usr/bin/env python3
"""
DataForge Automated Concurrency & Load Testing Tool.

Simulates concurrent request bursts against active API endpoints, calculates
precise performance latency percentiles, and verifies load capacity.

Usage:
    python3 scripts/run_load_test.py --url http://localhost:8000/health --concurrency 50 --requests 500
"""

import argparse
import asyncio
import sys
import time

import httpx


async def send_request(client: httpx.AsyncClient, url: str) -> float:
    start = time.time()
    try:
        resp = await client.get(url, timeout=5.0)
        status = resp.status_code
    except Exception:
        status = -1
    elapsed = time.time() - start
    return elapsed if status == 200 else -1.0


async def worker(url: str, num_requests: int, queue: asyncio.Queue, results: list):  # noqa: ARG001
    async with httpx.AsyncClient() as client:
        while True:
            try:
                _ = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            latency = await send_request(client, url)
            results.append(latency)
            queue.task_done()


async def run_load_test(url: str, concurrency: int, total_requests: int):
    print("=" * 70)
    print(f"Starting DataForge Load Test: {url}")
    print(f"Concurrency: {concurrency} workers | Total requests: {total_requests}")
    print("=" * 70)

    # Initialize task queue
    queue: asyncio.Queue[None] = asyncio.Queue()
    for _ in range(total_requests):
        queue.put_nowait(None)

    results: list[float] = []
    start_time = time.time()

    # Start workers
    workers = [asyncio.create_task(worker(url, total_requests, queue, results)) for _ in range(concurrency)]

    await queue.join()

    # Clean up workers
    for w in workers:
        w.cancel()

    total_elapsed = time.time() - start_time

    # Process results
    latencies = [r * 1000 for r in results if r >= 0.0]  # to ms
    failures = len(results) - len(latencies)

    if not latencies:
        print("\n[ERROR] All requests failed to connect or returned non-200 responses.")
        sys.exit(1)

    latencies.sort()
    count = len(latencies)

    avg_latency = sum(latencies) / count

    # Use ceiling division (clamped to at least 1) so percentile
    # indices never degenerate to 0 when the sample set is small —
    # otherwise p99 with N=1 == p50 == min, which is misleading.
    def _pct(q: float) -> float:
        idx = max(0, min(count - 1, int(count * q + 0.5) - 1))
        return latencies[idx]

    p50 = _pct(0.50)
    p90 = _pct(0.90)
    p95 = _pct(0.95)
    p99 = _pct(0.99)
    min_lat = latencies[0]
    max_lat = latencies[-1]
    rps = count / total_elapsed

    print("\nPerformance metrics:")
    print(f"  Total time elapsed:  {total_elapsed:.3f} seconds")
    print(f"  Successful requests: {count}/{len(results)} ({failures} failures)")
    print(f"  Requests/sec (RPS):  {rps:.2f}")
    print(f"  Minimum latency:     {min_lat:.2f} ms")
    print(f"  Average latency:     {avg_latency:.2f} ms")
    print(f"  p50 (median):        {p50:.2f} ms")
    print(f"  p90:                 {p90:.2f} ms")
    print(f"  p95:                 {p95:.2f} ms")
    print(f"  p99:                 {p99:.2f} ms")
    print(f"  Maximum latency:     {max_lat:.2f} ms")

    print("\nValidation Gate Status:")
    if failures > 0:
        print("  [FAIL] Failures detected during load test.")
        sys.exit(1)
    elif p95 > 250.0:
        print("  [FAIL] p95 latency exceeds 250ms threshold.")
        sys.exit(1)
    else:
        print("  [OK] Load test validation threshold passed successfully.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="DataForge Scraper Load Test Utility")
    parser.add_argument("--url", default="http://localhost:8000/health", help="Target URL to load test")
    parser.add_argument("--concurrency", type=int, default=30, help="Number of concurrent workers")
    parser.add_argument("--requests", type=int, default=300, help="Total requests to dispatch")

    args = parser.parse_args()

    # Run async loop
    try:
        asyncio.run(run_load_test(args.url, args.concurrency, args.requests))
    except KeyboardInterrupt:
        print("\nTest interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
