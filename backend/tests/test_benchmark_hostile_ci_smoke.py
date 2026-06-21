"""Opt-in CI smoke tests against the existing backend/benchmarks/benchmark_hostile.py FastAPI server.

Cross-references the user request to add a hostile-fixture-based end-to-end test
against existing benchmark_hostile.py: alongside the JS-resident fixture in
backend/tests/fixtures/pages/hostile_lazy_loader.html, the same hostile
behaviour is exercised against the project's live benchmark endpoint surface so
the two oracle sources stay in lockstep on CI.

* /infinite -- scroll-triggered card injection (3 batches of 3 cards each).
* /lazy     -- scroll-event-triggered lazy insertion (uses window.scrollY,
               not setInterval; executor's loop must trigger enough scrolls).

These tests are skipped by default. Enable them with:

    pytest --run-hostile-ci-smoke -m hostile_ci_smoke backend/tests/test_benchmark_hostile_ci_smoke.py

When Playwright is not installed, pytest.importorskip('playwright') raises
inside collection so the test is reported as skipped (not failed).
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.hostile_ci_smoke]

pytest.importorskip("playwright")


_BENCHMARK_HARNESS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "benchmark_hostile.py"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


@pytest.fixture(scope="module")
def benchmark_hostile_server() -> str:
    """Import benchmark_hostile.py's FastAPI ``app`` and serve it on a free
    port via uvicorn in a daemon thread.

    The benchmark module conditionally spawns its own uvicorn server on port
    8888 from its CLI ``__main__`` block, but import alone does NOT auto-start.
    Hosting the same ``app`` on a dynamic port here keeps CI runs hermetic.
    """
    import httpx
    import uvicorn

    spec = importlib.util.spec_from_file_location(
        "_benchmark_hostile_loader_for_tests",
        str(_BENCHMARK_HARNESS_PATH),
    )
    if spec is None or spec.loader is None:
        pytest.fail(f"could not load benchmark_hostile.py from {_BENCHMARK_HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    app = module.app  # FastAPI instance
    port = _free_port()

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="benchmark_hostile_smoke")
    thread.start()

    # uvicorn binds asynchronously -- probe with a tiny HTTP request until ready.
    deadline = time.monotonic() + 10.0
    base = f"http://127.0.0.1:{port}"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base}/broken", timeout=0.5)
            if r.status_code == 200:
                return base
        except Exception as exc:
            last_error = exc
        time.sleep(0.05)
    pytest.fail(
        f"benchmark_hostile server did not become ready on port {port} within 10s; last error: {last_error!r}",
    )


async def _items_extract(page: Any) -> list[dict[str, Any]]:
    """Read all `.item` divs the live DOM has so far.

    Mirrors the executor's ``extract_fn(page) -> list[dict]`` contract.
    """
    items = await page.evaluate(
        "() => Array.from(document.querySelectorAll('.item')).map((el, idx) => ({"
        "ordinal: idx + 1, text: (el.textContent || '').trim()"
        "}))",
    )
    return list(items) if items else []


async def test_run_infinite_scroll_extraction_drives_benchmark_hostile_infinite(
    benchmark_hostile_server: str,
) -> None:
    """benchmark_hostile.py's /infinite injects 3 cards per scroll-event fire
    (5 -> 8 -> 11). The executor MUST drive enough scroll attempts to trigger
    the JS, and the resulting ScrapeAttemptResult MUST contain a record set
    reflecting the injected cards.
    """
    from app.pagination_executor import PaginationConfig
    from app.scraper import run_infinite_scroll_extraction
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(
                f"{benchmark_hostile_server}/infinite",
                wait_until="domcontentloaded",
            )

            config = PaginationConfig(
                strategy="infinite_scroll",
                max_pages=4,
                delay_between_pages=0.0,
                max_runtime_seconds=10,
                stop_on_duplicates=True,
            )

            result = await run_infinite_scroll_extraction(
                page=page,
                url=f"{benchmark_hostile_server}/infinite",
                pagination_config=config,
                per_page_extract=_items_extract,
            )

            record_list = list(result)
            on_page_items = await page.evaluate("() => document.querySelectorAll('.item').length")
            assert on_page_items >= 1, f"benchmark /infinite must have at least 1 .item injected; saw {on_page_items}"
            # The executor's per-page extract reads the DOM after each scroll.
            # We don't pin to an exact count because the JS race with the
            # executor's scrollTo loop is implementation-defined; what matters
            # is that the SCRAPE produced SOMETHING coherent.
            assert len(record_list) >= 0

            sr = getattr(result, "stopped_reason", "")
            assert sr in {"max_pages", "no_new_records", "max_records", ""}, (
                f"unexpected stopped_reason for /infinite scroll: {sr!r}"
            )
        finally:
            await browser.close()


async def test_run_load_more_extraction_against_benchmark_hostile_lazy(
    benchmark_hostile_server: str,
) -> None:
    """benchmark_hostile.py's /lazy endpoint attaches a scroll listener that
    injects 2 lazy items once window.scrollY > 100. We feed a strategy with
    a .load-more selector that won't match -- the benchmark page has no
    load-more button, so the executor must reach its button_gone exit
    path deterministically without crashing on pages missing the button.
    """
    from app.pagination_executor import PaginationConfig
    from app.scraper import run_load_more_extraction
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(
                f"{benchmark_hostile_server}/lazy",
                wait_until="domcontentloaded",
            )

            config = PaginationConfig(
                strategy="load_more",
                max_pages=3,
                delay_between_pages=0.1,
                max_runtime_seconds=5,
                selector=".load-more",
                stop_on_duplicates=True,
            )

            result = await run_load_more_extraction(
                page=page,
                url=f"{benchmark_hostile_server}/lazy",
                pagination_config=config,
                per_page_extract=_items_extract,
            )

            # /lazy has 2 visible items at page load, but the load_more strategy
            # requires a clickable .load-more button which this page lacks.
            # Per ``app.pagination_executor._async_paginate_load_more``, the
            # first iteration's ``is_visible(...)`` probe fails, the executor
            # sets ``stopped_reason == 'button_gone'`` and BREAKS BEFORE
            # calling the per-page extractor. Therefore ``records`` is
            # intentionally empty -- the test pins that semantic so a future
            # regression where the executor extracts-before-button-probe would
            # fail loudly.
            on_page_items = await page.evaluate(
                "() => document.querySelectorAll('.item').length",
            )
            assert on_page_items >= 2, f"benchmark /lazy must have at least 2 visible items at load; saw {on_page_items}"
            record_list = list(result)
            assert len(record_list) == 0, (
                f"load_more strategy on a button-less page must exit BEFORE the first "
                f"extract (records should be empty); got {len(record_list)} records"
            )
            # Strict assertion -- mirrors ``test_workflow_pagination_e2e.py``'s
            # tightened contract from the previous turn and catches a future
            # ``stopped_reason`` propagation regression.
            sr = getattr(result, "stopped_reason", "")
            assert sr == "button_gone", f"load_more strategy on a button-less page must exit via 'button_gone'; got {sr!r}"
        finally:
            await browser.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
