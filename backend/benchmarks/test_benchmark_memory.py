"""Memory-leak benchmark for the extraction pipeline.

Runs a single extraction loop N times against loopback HTTP endpoints
and asserts that memory consumption stays bounded. Memory growth beyond
a 1.5× baseline or any iteration exceeding 512 MB fails the benchmark.

Marked ``@pytest.mark.slow`` and ``@pytest.mark.resource`` so it can
be skipped in fast CI runs.
"""

from __future__ import annotations

import gc
import http.server
import socket
import threading
import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.resource]


# ─── Mock Server ─────────────────────────────────────────────────────────────


class _MemoryBenchHandler(http.server.BaseHTTPRequestHandler):
    """Stable handler that serves deterministic HTML."""

    def log_message(self, _format, *args) -> None:
        pass

    _HTML = """
    <!DOCTYPE html>
    <html><body>
      <div class="product">
        <h3 class="name">Widget Alpha</h3>
        <span class="price">$10.00</span>
      </div>
      <div class="product">
        <h3 class="name">Widget Beta</h3>
        <span class="price">$20.00</span>
      </div>
      <div class="product">
        <h3 class="name">Widget Gamma</h3>
        <span class="price">$30.00</span>
      </div>
    </body></html>
    """.strip()

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self._HTML)))
        self.end_headers()
        self.wfile.write(self._HTML.encode())


@contextmanager
def _loopback_server() -> Iterator[str]:
    """Spin up a loopback HTTP server, yield its base URL, then shut down."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MemoryBenchHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/products"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _http_get(url: str, timeout: float = 5.0) -> bytes:
    """Tiny stdlib HTTP GET to keep the test free of client dependencies."""
    parts = urllib_parse(url)
    with socket.create_connection((parts.hostname, parts.port), timeout=timeout) as sock:
        sock.sendall(f"GET {parts.path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        buf = bytearray()
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf.extend(chunk)
    # Strip HTTP headers
    sep = buf.find(b"\r\n\r\n")
    return bytes(buf[sep + 4 :]) if sep != -1 else bytes(buf)


def urllib_parse(url: str):
    """Tiny urlparse replacement to avoid the urllib import side-effects in some test envs."""
    from urllib.parse import urlparse

    return urlparse(url)


# ─── Memory Benchmark ────────────────────────────────────────────────────────


@pytest.mark.timeout(120)
def test_memory_stability_over_100_extractions() -> None:
    """100 sequential extractions must not leak memory beyond 1.5× baseline.

    Reads HTML from a loopback HTTP server, runs the regex extractor 100
    times, and asserts that tracemalloc-tracked memory growth stays bounded.
    """
    from app.models import FieldType, SchemaField
    from app.selector_engine import extract_with_regex

    schema = [
        SchemaField(name="name", field_type=FieldType.STRING, required=True),
        SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
    ]

    tracemalloc.start()
    gc.collect()

    with _loopback_server() as url:
        # Warm-up: load module + first extraction
        html = _http_get(url)
        extract_with_regex(html.decode(), schema)

        baseline_current, baseline_peak = tracemalloc.get_traced_memory()
        samples: list[tuple[int, int]] = []
        max_peak_mb = 0.0

        for i in range(100):
            html = _http_get(url)
            extract_with_regex(html.decode(), schema)
            current, peak = tracemalloc.get_traced_memory()
            samples.append((current, peak))
            peak_mb = peak / (1024 * 1024)
            max_peak_mb = max(max_peak_mb, peak_mb)
            if i % 10 == 0:
                gc.collect()

        gc.collect()
        final_current, final_peak = tracemalloc.get_traced_memory()

    tracemalloc.stop()

    # Compute growth ratio using the average post-warmup current as denominator.
    mid_current = sum(c for c, _ in samples[20:80]) / max(1, len(samples[20:80]))
    final_growth_ratio = final_current / max(1, baseline_current)

    # Assertions
    assert max_peak_mb < 512.0, f"Peak memory {max_peak_mb:.1f} MB exceeded 512 MB ceiling during 100 extraction iterations"
    assert final_growth_ratio < 1.5, (
        f"Memory growth ratio {final_growth_ratio:.3f} exceeded 1.5× baseline "
        f"(baseline={baseline_current / 1024:.1f} KB, "
        f"final={final_current / 1024:.1f} KB, "
        f"mid_iteration={mid_current / 1024:.1f} KB)"
    )
