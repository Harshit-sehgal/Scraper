"""Comprehensive Benchmark Suite with Enforceable Thresholds.

This module provides real extraction benchmarks with strict performance,
accuracy, and resource usage thresholds that must be met for production readiness.

Benchmarks cover:
1. Extraction Accuracy (F1, precision, recall)
2. Performance (latency, throughput, concurrent jobs)
3. Resource Usage (memory, CPU)
4. Reliability (error rates, timeout rates)
5. Scalability (concurrent job handling)

Usage:
    # Run all benchmarks
    pytest backend/benchmarks/test_benchmark_enforceable.py -v

    # Run specific benchmark categories
    pytest backend/benchmarks/test_benchmark_enforceable.py -v -m accuracy
    pytest backend/benchmarks/test_benchmark_enforceable.py -v -m performance
    pytest backend/benchmarks/test_benchmark_enforceable.py -v -m resource
    pytest backend/benchmarks/test_benchmark_enforceable.py -v -m scalability
"""

from __future__ import annotations

import asyncio
import http.server
import json
import logging
import os
import sys
import threading
import time
import urllib.parse

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logger = logging.getLogger(__name__)

# ─── Thresholds ──────────────────────────────────────────────────────────────

THRESHOLDS = {
    # Accuracy thresholds
    "min_f1_score": 0.75,
    "min_precision": 0.70,
    "min_recall": 0.70,
    "min_field_accuracy": 0.80,
    "min_record_completeness": 0.60,
    # Performance thresholds (ms)
    "max_p50_latency": 2000,
    "max_p95_latency": 5000,
    "max_p99_latency": 10000,
    "max_avg_latency": 3000,
    # Throughput thresholds
    "min_records_per_second": 5,
    "min_pages_per_minute": 30,
    # Reliability thresholds
    "max_error_rate": 0.10,  # 10%
    "max_timeout_rate": 0.05,  # 5%
    "min_success_rate": 0.90,  # 90%
    # Resource thresholds
    "max_memory_mb": 512,
    "max_cpu_percent": 80,
    # Scalability thresholds
    "min_concurrent_jobs": 10,
    "max_concurrent_latency_ms": 15000,
    "min_throughput_under_load": 3,
}

# ─── Mock Server ─────────────────────────────────────────────────────────────


class BenchmarkHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for benchmark test pages."""

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/books":
            self._send_html("""
            <html>
            <body>
              <div class="book">
                <h2 class="title">The Great Gatsby</h2>
                <span class="price">$15.99</span>
                <span class="rating">5 stars</span>
              </div>
              <div class="book">
                <h2 class="title">To Kill a Mockingbird</h2>
                <span class="price">$12.49</span>
                <span class="rating">4 stars</span>
              </div>
              <div class="book">
                <h2 class="title">1984</h2>
                <span class="price">$9.99</span>
                <span class="rating">5 stars</span>
              </div>
            </body>
            </html>
            """)
        elif path == "/quotes":
            self._send_html("""
            <html>
            <body>
              <div class="quote">
                <p class="text">"Be yourself; everyone else is already taken."</p>
                <small class="author">Oscar Wilde</small>
              </div>
              <div class="quote">
                <p class="text">"So many books, so little time."</p>
                <small class="author">Frank Zappa</small>
              </div>
            </body>
            </html>
            """)
        elif path == "/products":
            self._send_html("""
            <html>
            <body>
              <div class="product">
                <h3 class="name">Laptop</h3>
                <span class="price">$999.99</span>
                <span class="category">Electronics</span>
              </div>
              <div class="product">
                <h3 class="name">Phone</h3>
                <span class="price">$699.99</span>
                <span class="category">Electronics</span>
              </div>
            </body>
            </html>
            """)
        elif path == "/slow":
            time.sleep(0.5)
            self._send_html("<html><body><h1>Slow Page</h1></body></html>")
        elif path == "/error":
            self.send_error(500)
        elif path == "/timeout":
            time.sleep(10)
            self._send_html("<html><body><h1>Timeout</h1></body></html>")
        else:
            self._send_html("<html><body><h1>Default</h1></body></html>")

    def _send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def benchmark_server():
    """Start a local HTTP server for benchmarks."""
    server = http.server.HTTPServer(("127.0.0.1", 0), BenchmarkHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def accuracy_schema():
    """Schema for accuracy benchmarks."""
    return {
        "books": [
            SchemaField(name="title", field_type=FieldType.STRING, description="Book title", required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="Book price", required=True),
            SchemaField(name="rating", field_type=FieldType.STRING, description="Star rating", required=False),
        ],
        "quotes": [
            SchemaField(name="text", field_type=FieldType.STRING, description="Quote text", required=True),
            SchemaField(name="author", field_type=FieldType.STRING, description="Quote author", required=True),
        ],
        "products": [
            SchemaField(name="name", field_type=FieldType.STRING, description="Product name", required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="Product price", required=True),
            SchemaField(name="category", field_type=FieldType.STRING, description="Product category", required=False),
        ],
    }


@pytest.fixture
def expected_data():
    """Expected extraction results for accuracy measurement."""
    return {
        "books": [
            {"title": "The Great Gatsby", "price": "$15.99", "rating": "5 stars"},
            {"title": "To Kill a Mockingbird", "price": "$12.49", "rating": "4 stars"},
            {"title": "1984", "price": "$9.99", "rating": "5 stars"},
        ],
        "quotes": [
            {"text": "Be yourself; everyone else is already taken.", "author": "Oscar Wilde"},
            {"text": "So many books, so little time.", "author": "Frank Zappa"},
        ],
        "products": [
            {"name": "Laptop", "price": "$999.99", "category": "Electronics"},
            {"name": "Phone", "price": "$699.99", "category": "Electronics"},
        ],
    }


# ─── Helper Functions ────────────────────────────────────────────────────────


def calculate_metrics(
    extracted: list[dict],
    expected: list[dict],
    fields: list[str],
) -> dict[str, float]:
    """Calculate precision, recall, F1, and field accuracy."""
    if not extracted or not expected:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "field_accuracy": 0.0}

    # Simple matching based on first required field
    extracted_set = {json.dumps({k: v for k, v in r.items() if k in fields}, sort_keys=True) for r in extracted}
    expected_set = {json.dumps({k: v for k, v in r.items() if k in fields}, sort_keys=True) for r in expected}

    tp = len(extracted_set & expected_set)
    fp = len(extracted_set - expected_set)
    fn = len(expected_set - extracted_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Field accuracy
    field_matches = 0
    field_total = 0
    for ext in extracted:
        for exp in expected:
            matches = sum(1 for f in fields if ext.get(f) == exp.get(f))
            field_matches += matches
            field_total += len(fields)

    field_accuracy = field_matches / field_total if field_total > 0 else 0.0

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "field_accuracy": round(field_accuracy, 3),
    }


def calculate_percentiles(latencies: list[float]) -> dict[str, float]:
    """Calculate latency percentiles."""
    if not latencies:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    p50_idx = int(n * 0.50)
    p95_idx = int(n * 0.95)
    p99_idx = int(n * 0.99)

    return {
        "p50": round(sorted_latencies[min(p50_idx, n - 1)], 1),
        "p95": round(sorted_latencies[min(p95_idx, n - 1)], 1),
        "p99": round(sorted_latencies[min(p99_idx, n - 1)], 1),
    }


# ─── Accuracy Benchmarks ─────────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.accuracy
@pytest.mark.asyncio
async def test_extraction_accuracy_books(benchmark_server, accuracy_schema, expected_data):
    """Benchmark extraction accuracy for book listings."""
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]
    expected = expected_data["books"]
    fields = ["title", "price", "rating"]

    start = time.time()
    results = await scrape_url(url=url, schema_fields=schema)
    _latency_ms = (time.time() - start) * 1000

    metrics = calculate_metrics(results, expected, fields)

    assert metrics["f1"] >= THRESHOLDS["min_f1_score"], (
        f"Books F1 score {metrics['f1']} below threshold {THRESHOLDS['min_f1_score']}"
    )
    assert metrics["precision"] >= THRESHOLDS["min_precision"], (
        f"Books precision {metrics['precision']} below threshold {THRESHOLDS['min_precision']}"
    )
    assert metrics["recall"] >= THRESHOLDS["min_recall"], (
        f"Books recall {metrics['recall']} below threshold {THRESHOLDS['min_recall']}"
    )
    assert metrics["field_accuracy"] >= THRESHOLDS["min_field_accuracy"], (
        f"Books field accuracy {metrics['field_accuracy']} below threshold {THRESHOLDS['min_field_accuracy']}"
    )


@pytest.mark.browser
@pytest.mark.accuracy
@pytest.mark.asyncio
async def test_extraction_accuracy_quotes(benchmark_server, accuracy_schema, expected_data):
    """Benchmark extraction accuracy for quote listings."""
    url = f"{benchmark_server}/quotes"
    schema = accuracy_schema["quotes"]
    expected = expected_data["quotes"]
    fields = ["text", "author"]

    results = await scrape_url(url=url, schema_fields=schema)
    metrics = calculate_metrics(results, expected, fields)

    assert metrics["f1"] >= THRESHOLDS["min_f1_score"], (
        f"Quotes F1 score {metrics['f1']} below threshold {THRESHOLDS['min_f1_score']}"
    )


@pytest.mark.browser
@pytest.mark.accuracy
@pytest.mark.asyncio
async def test_extraction_accuracy_products(benchmark_server, accuracy_schema, expected_data):
    """Benchmark extraction accuracy for product listings."""
    url = f"{benchmark_server}/products"
    schema = accuracy_schema["products"]
    expected = expected_data["products"]
    fields = ["name", "price", "category"]

    results = await scrape_url(url=url, schema_fields=schema)
    metrics = calculate_metrics(results, expected, fields)

    assert metrics["f1"] >= THRESHOLDS["min_f1_score"], (
        f"Products F1 score {metrics['f1']} below threshold {THRESHOLDS['min_f1_score']}"
    )


@pytest.mark.browser
@pytest.mark.accuracy
@pytest.mark.asyncio
async def test_record_completeness(benchmark_server, accuracy_schema, expected_data):
    """Benchmark record completeness across all test cases."""
    test_cases = [
        ("/books", accuracy_schema["books"], expected_data["books"], ["title", "price"]),
        ("/quotes", accuracy_schema["quotes"], expected_data["quotes"], ["text", "author"]),
        ("/products", accuracy_schema["products"], expected_data["products"], ["name", "price"]),
    ]

    completeness_scores = []

    for path, schema, expected, fields in test_cases:
        url = f"{benchmark_server}{path}"
        results = await scrape_url(url=url, schema_fields=schema)

        if results and expected:
            # Calculate completeness as percentage of expected fields found
            total_fields = len(fields) * len(expected)
            found_fields = 0

            for exp in expected:
                for result in results:
                    matches = sum(1 for f in fields if result.get(f) == exp.get(f))
                    found_fields += matches

            completeness = found_fields / total_fields if total_fields > 0 else 0.0
            completeness_scores.append(completeness)

    avg_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0

    assert avg_completeness >= THRESHOLDS["min_record_completeness"], (
        f"Average record completeness {avg_completeness:.3f} below threshold {THRESHOLDS['min_record_completeness']}"
    )


# ─── Performance Benchmarks ──────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.performance
@pytest.mark.asyncio
async def test_single_extraction_latency(benchmark_server, accuracy_schema):
    """Benchmark single extraction latency."""
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    latencies = []

    for _ in range(10):
        start = time.time()
        await scrape_url(url=url, schema_fields=schema)
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)

    percentiles = calculate_percentiles(latencies)
    avg_latency = sum(latencies) / len(latencies)

    assert percentiles["p50"] <= THRESHOLDS["max_p50_latency"], (
        f"P50 latency {percentiles['p50']}ms exceeds threshold {THRESHOLDS['max_p50_latency']}ms"
    )
    assert percentiles["p95"] <= THRESHOLDS["max_p95_latency"], (
        f"P95 latency {percentiles['p95']}ms exceeds threshold {THRESHOLDS['max_p95_latency']}ms"
    )
    assert avg_latency <= THRESHOLDS["max_avg_latency"], (
        f"Average latency {avg_latency:.1f}ms exceeds threshold {THRESHOLDS['max_avg_latency']}ms"
    )


@pytest.mark.browser
@pytest.mark.performance
@pytest.mark.asyncio
async def test_throughput(benchmark_server, accuracy_schema):
    """Benchmark extraction throughput (records per second)."""
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    start = time.time()
    total_records = 0

    for _ in range(20):
        results = await scrape_url(url=url, schema_fields=schema)
        total_records += len(results)

    elapsed = time.time() - start
    records_per_second = total_records / elapsed

    assert records_per_second >= THRESHOLDS["min_records_per_second"], (
        f"Throughput {records_per_second:.2f} records/s below threshold {THRESHOLDS['min_records_per_second']}"
    )


@pytest.mark.browser
@pytest.mark.performance
@pytest.mark.asyncio
async def test_pages_per_minute(benchmark_server, accuracy_schema):
    """Benchmark pages per minute extraction rate."""
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    start = time.time()
    pages_scraped = 0

    for _ in range(10):
        await scrape_url(url=url, schema_fields=schema)
        pages_scraped += 1

    elapsed = time.time() - start
    pages_per_minute = (pages_scraped / elapsed) * 60

    assert pages_per_minute >= THRESHOLDS["min_pages_per_minute"], (
        f"Pages per minute {pages_per_minute:.2f} below threshold {THRESHOLDS['min_pages_per_minute']}"
    )


# ─── Reliability Benchmarks ──────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.reliability
@pytest.mark.asyncio
async def test_error_rate(benchmark_server, accuracy_schema):
    """Benchmark extraction error rate."""
    test_urls = [
        f"{benchmark_server}/books",
        f"{benchmark_server}/quotes",
        f"{benchmark_server}/products",
        f"{benchmark_server}/error",
        f"{benchmark_server}/nonexistent",
    ]

    successes = 0
    failures = 0

    for url in test_urls:
        try:
            results = await scrape_url(url=url, schema_fields=accuracy_schema["books"])
            if results:
                successes += 1
            else:
                failures += 1
        except Exception:
            failures += 1

    total = successes + failures
    error_rate = failures / total if total > 0 else 1.0

    assert error_rate <= THRESHOLDS["max_error_rate"], (
        f"Error rate {error_rate:.3f} exceeds threshold {THRESHOLDS['max_error_rate']}"
    )


@pytest.mark.browser
@pytest.mark.reliability
@pytest.mark.asyncio
async def test_timeout_rate(benchmark_server, accuracy_schema):
    """Benchmark extraction timeout rate."""
    test_urls = [
        f"{benchmark_server}/books",
        f"{benchmark_server}/quotes",
        f"{benchmark_server}/slow",
    ]

    timeouts = 0
    total = 0

    for url in test_urls:
        total += 1
        try:
            await asyncio.wait_for(
                scrape_url(url=url, schema_fields=accuracy_schema["books"]),
                timeout=5.0,
            )
        except TimeoutError:
            timeouts += 1
        except Exception:
            pass

    timeout_rate = timeouts / total if total > 0 else 1.0

    assert timeout_rate <= THRESHOLDS["max_timeout_rate"], (
        f"Timeout rate {timeout_rate:.3f} exceeds threshold {THRESHOLDS['max_timeout_rate']}"
    )


@pytest.mark.browser
@pytest.mark.reliability
@pytest.mark.asyncio
async def test_success_rate(benchmark_server, accuracy_schema):
    """Benchmark extraction success rate."""
    test_urls = [
        f"{benchmark_server}/books",
        f"{benchmark_server}/quotes",
        f"{benchmark_server}/products",
    ]

    successes = 0
    total = len(test_urls)

    for url in test_urls:
        try:
            results = await scrape_url(url=url, schema_fields=accuracy_schema["books"])
            if results:
                successes += 1
        except Exception:
            pass

    success_rate = successes / total if total > 0 else 0.0

    assert success_rate >= THRESHOLDS["min_success_rate"], (
        f"Success rate {success_rate:.3f} below threshold {THRESHOLDS['min_success_rate']}"
    )


# ─── Resource Benchmarks ─────────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.resource
@pytest.mark.asyncio
async def test_memory_usage(benchmark_server, accuracy_schema):
    """Benchmark memory usage during extraction."""
    import tracemalloc

    tracemalloc.start()

    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    # Run multiple extractions
    for _ in range(50):
        await scrape_url(url=url, schema_fields=schema)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / 1024 / 1024

    assert peak_mb <= THRESHOLDS["max_memory_mb"], (
        f"Peak memory {peak_mb:.2f}MB exceeds threshold {THRESHOLDS['max_memory_mb']}MB"
    )


@pytest.mark.browser
@pytest.mark.resource
@pytest.mark.asyncio
async def test_cpu_usage(benchmark_server, accuracy_schema):
    """Benchmark CPU usage during extraction."""

    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    # Measure CPU time
    start_cpu = time.process_time()
    start_wall = time.time()

    for _ in range(20):
        await scrape_url(url=url, schema_fields=schema)

    cpu_time = time.process_time() - start_cpu
    wall_time = time.time() - start_wall

    cpu_percent = (cpu_time / wall_time) * 100 if wall_time > 0 else 0

    assert cpu_percent <= THRESHOLDS["max_cpu_percent"], (
        f"CPU usage {cpu_percent:.1f}% exceeds threshold {THRESHOLDS['max_cpu_percent']}%"
    )


# ─── Scalability Benchmarks ──────────────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.scalability
@pytest.mark.asyncio
async def test_concurrent_jobs(benchmark_server, accuracy_schema):
    """Benchmark concurrent job handling."""
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    async def extract_job():
        start = time.time()
        results = await scrape_url(url=url, schema_fields=schema)
        latency = (time.time() - start) * 1000
        return len(results), latency

    # Run concurrent jobs
    tasks = [extract_job() for _ in range(THRESHOLDS["min_concurrent_jobs"])]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    latencies = [r[1] for r in successes]

    assert len(successes) >= THRESHOLDS["min_concurrent_jobs"] * 0.8, (
        f"Only {len(successes)}/{THRESHOLDS['min_concurrent_jobs']} concurrent jobs succeeded"
    )

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency <= THRESHOLDS["max_concurrent_latency_ms"], (
            f"Average concurrent latency {avg_latency:.1f}ms exceeds threshold {THRESHOLDS['max_concurrent_latency_ms']}ms"
        )


@pytest.mark.browser
@pytest.mark.scalability
@pytest.mark.asyncio
async def test_throughput_under_load(benchmark_server, accuracy_schema):
    """Benchmark throughput under concurrent load."""
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]

    async def extract_job():
        results = await scrape_url(url=url, schema_fields=schema)
        return len(results)

    start = time.time()

    # Run 10 concurrent jobs
    tasks = [extract_job() for _ in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start
    total_records = sum(r for r in results if not isinstance(r, Exception))
    throughput = total_records / elapsed

    assert throughput >= THRESHOLDS["min_throughput_under_load"], (
        f"Throughput under load {throughput:.2f} records/s below threshold {THRESHOLDS['min_throughput_under_load']}"
    )


# ─── Comprehensive Benchmark Report ──────────────────────────────────────────


@pytest.mark.browser
@pytest.mark.comprehensive
@pytest.mark.asyncio
async def test_comprehensive_benchmark_report(benchmark_server, accuracy_schema, expected_data):
    """Generate a comprehensive benchmark report with all metrics."""
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "thresholds": THRESHOLDS,
        "accuracy": {},
        "performance": {},
        "reliability": {},
        "resources": {},
        "scalability": {},
    }

    # Accuracy tests
    for name, schema, expected, fields in [
        ("books", accuracy_schema["books"], expected_data["books"], ["title", "price"]),
        ("quotes", accuracy_schema["quotes"], expected_data["quotes"], ["text", "author"]),
        ("products", accuracy_schema["products"], expected_data["products"], ["name", "price"]),
    ]:
        url = f"{benchmark_server}/{name}"
        results = await scrape_url(url=url, schema_fields=schema)
        metrics = calculate_metrics(results, expected, fields)
        report["accuracy"][name] = metrics

    # Performance tests
    url = f"{benchmark_server}/books"
    schema = accuracy_schema["books"]
    latencies = []

    for _ in range(10):
        start = time.time()
        await scrape_url(url=url, schema_fields=schema)
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)

    report["performance"]["latencies"] = calculate_percentiles(latencies)
    report["performance"]["avg_latency_ms"] = round(sum(latencies) / len(latencies), 1)

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), "benchmark_report.json")
    with open(report_path, "w") as f:  # noqa: ASYNC230
        json.dump(report, f, indent=2)

    # Verify all thresholds
    avg_f1 = sum(m["f1"] for m in report["accuracy"].values()) / len(report["accuracy"])
    assert avg_f1 >= THRESHOLDS["min_f1_score"], f"Average F1 {avg_f1:.3f} below threshold {THRESHOLDS['min_f1_score']}"
