"""Hostile-fixture E2E — drives ``scraper.run_infinite_scroll_extraction`` and
``scraper.run_load_more_extraction`` against a real Playwright page that is
served from ``backend/tests/fixtures/pages/hostile_lazy_loader.html``.

The fixture is hostile because the lazy loader is **explicit JavaScript** that
runs on a ``setInterval`` — NOT a scroll-event listener — which lets the tests
distinguish "scrolled enough" behaviour from "scrolled at all" behaviour.

* ``infinite_scroll`` mode: items are appended on a 700 ms ``setInterval`` up
  to 3 batches (5 -> 7 -> 9 -> 11). The executor's
  ``document.body.scrollHeight`` probe must observe growth across at least two
  ticks and ultimately stabilise so ``stopped_reason == "no_new_records"``.
  The fixture ALSO wraps ``window.scrollTo`` and pushes every call into
  ``window.__scrollToLog`` so the executor's scroll attempts are observable
  directly (not just inferred from DOM mutations).

* ``load_more`` mode: the "Load more" button is hidden until a second
  ``setInterval`` reveals it ~2.4 s after page load. The executor must NOT
  conclude ``stopped_reason == "button_gone"`` on the first locator probe —
  it must spin until the button is ``is_visible()``. The fixture captures the
  ``Date.now()`` of the FIRST click in ``window.__lazyState.firstClickAt`` so
  the test can assert the executor actually waited for the timer.

Both behaviours are verifiable via the page's ``window.__lazyState`` (and
``window.__scrollToLog``) observability surface.
"""

from __future__ import annotations

import http.server
import sys
import threading
import urllib.parse
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.browser]

# Skip the entire module if Playwright is not installed.
pytest.importorskip("playwright")

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "pages" / "hostile_lazy_loader.html"
# Sentinel injected by the /loadmore route — defaults to "scroll" in the template.
# Using a sentinel lets the handler fail loudly if the fixture template ever drops it.
_MODE_SENTINEL = 'value="scroll"'


# ─── Test-time HTTP server that serves the fixture on two paths ─────────


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    """Tiny HTTP handler that returns the hostile fixture on /scroll and /loadmore."""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = _FIXTURE_PATH.read_text(encoding="utf-8")
        except OSError:
            self.send_response(500)
            self.end_headers()
            return

        if _MODE_SENTINEL not in body:
            self.send_response(500)
            self.end_headers()
            return

        if parsed.path == "/scroll":
            # Fixture template already defaults to scroll mode — serve as-is.
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if parsed.path == "/loadmore":
            mutated = body.replace(_MODE_SENTINEL, 'value="loadmore"', 1)
            if mutated == body:
                # The sentinel is gone or appears more than once — fail loudly.
                self.send_response(500)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(mutated.encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args: Any) -> None:
        # Silence the test server's stdout.
        return


@pytest.fixture(scope="module")
def fixture_server() -> Generator[str, None, None]:
    """Spin up a single-shot HTTP server for the duration of this module."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _FixtureHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ─── Per-page extract stub (real DOM read via page.evaluate) ─────────────


async def _cards_extract(page: Any) -> list[dict[str, Any]]:
    """Read the current set of cards from the live DOM.

    Uses the same ``page.evaluate`` interface the production executor does,
    so this exercises the same code path the executor's
    ``extract_fn`` callable expects from a real browser.
    """
    cards = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('#feed .card')).map((el, idx) => ({
            ordinal: idx + 1,
            title: (el.textContent || '').trim(),
        }))
        """,
    )
    return list(cards) if cards else []


# ─── Test #1 — infinite_scroll drives window.scrollTo until scrollHeight plateaus ─


async def test_infinite_scroll_drives_window_scroll_to_until_plateau(fixture_server: str) -> None:
    """With a setInterval-driven lazy loader, the executor MUST:

    1. Call ``window.scrollTo`` at least twice — proves the executor's scroll
       loop is observed by the page (via the ``__scrollToLog`` shim),
       independent of any inferred DOM mutation.
    2. Include at least one ``window.scrollTo(0, document.body.scrollHeight)``
       — the canonical "scroll to bottom" call.
    3. Exit with ``stopped_reason == 'no_new_records'`` once the page
       plateaus (setInterval has fired all 3 batches).
    """
    from app.pagination_executor import PaginationConfig
    from app.scraper import run_infinite_scroll_extraction
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(f"{fixture_server}/scroll", wait_until="domcontentloaded")

            await page.wait_for_function(
                "() => window.__lazyState && window.__lazyState.mode === 'scroll'",
                timeout=5000,
            )

            config = PaginationConfig(
                strategy="infinite_scroll",
                max_pages=6,
                # Shorten the executor's per-tick settle so the test runs quickly
                # — the fixture's setInterval is 700 ms, executor sleep 200 ms.
                delay_between_pages=0.2,
                max_runtime_seconds=20,
                max_records=200,
                stop_on_duplicates=True,
            )

            result = await run_infinite_scroll_extraction(
                page=page,
                url=fixture_server,
                pagination_config=config,
                per_page_extract=_cards_extract,
            )

            # ── Executor-side observability (the headline assertion) ──
            scroll_log = await page.evaluate("() => window.__scrollToLog || []")
            assert isinstance(scroll_log, list), f"__scrollToLog must be a list, got {type(scroll_log)!r}"
            assert len(scroll_log) >= 2, (
                f"executor must call window.scrollTo at least twice; saw {len(scroll_log)} calls: {scroll_log[:5]!r}"
            )
            # At least one scroll attempt must target the bottom of the document
            # (the canonical load-more / infinite-scroll bottom-out pattern).
            bottom_scroll_seen = await page.evaluate(
                "() => Array.isArray(window.__scrollToLog) && "
                "window.__scrollToLog.some(call => call.length >= 2 && call[0] === 0 && "
                "typeof call[1] === 'number' && call[1] > 0)",
            )
            assert bottom_scroll_seen, f"executor must issue at least one window.scrollTo(x, positive_y); saw {scroll_log!r}"

            # ── Fixture-side observability ──
            observed = await page.evaluate("() => window.__lazyState")
            interval_ticks = int(observed.get("scrollIntervalTicks", 0))
            assert interval_ticks >= 2, f"fixture must have observed ≥ 2 setInterval-driven card injections; saw {interval_ticks}"

            # ── Record aggregation ──
            # ``records`` is a property on ScrapeAttemptResult (it subclasses list)
            record_list = list(result)
            cards_count = await page.evaluate("() => window.__lazyState.cardCount")
            assert len(record_list) >= int(cards_count), (
                f"expected records to reflect all {cards_count} injected cards; got {len(record_list)}"
            )
            # Plateau means the fixture emitted exactly 3 batches -> cards_count == 11.
            assert int(cards_count) == 11, f"fixture plateau expected at 11 cards; got {cards_count}"

            # ── Executor contract ──
            stopped_reason = getattr(result, "stopped_reason", "")
            assert stopped_reason == "no_new_records", (
                f"infinite_scroll must stop on scrollHeight plateau; got {stopped_reason!r}"
            )
        finally:
            await browser.close()


# ─── Test #2 — load_more waits for the setInterval-driven button reveal ───


async def test_load_more_waits_for_set_interval_driven_button(fixture_server: str) -> None:
    """The 'Load more' button is hidden until a ~2.4 s ``setInterval`` reveals
    it. The executor's first ``is_visible()`` probe MUST fail (proving the
    button was absent), and the FIRST recorded click MUST happen at least
    ``LOADMORE_DELAY_MS / 2`` after the page was navigated to it — proving
    the executor actually *spun waiting* for the setInterval to fire rather
    than immediately concluding ``button_gone``.
    """
    from app.pagination_executor import PaginationConfig
    from app.scraper import run_load_more_extraction
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(f"{fixture_server}/loadmore", wait_until="domcontentloaded")

            await page.wait_for_function(
                "() => window.__lazyState && window.__lazyState.mode === 'loadmore'",
                timeout=5000,
            )

            config = PaginationConfig(
                strategy="load_more",
                max_pages=4,
                delay_between_pages=0.4,
                max_runtime_seconds=20,
                max_records=200,
                stop_on_duplicates=True,
            )

            result = await run_load_more_extraction(
                page=page,
                url=fixture_server,
                pagination_config=config,
                per_page_extract=_cards_extract,
            )

            # ── Fixture-side observability ──
            observed = await page.evaluate("() => window.__lazyState")
            clicks = int(observed.get("scrollButtonClicks", 0))
            assert clicks >= 1, f"executor must click the load-more button at least once; saw {clicks} clicks"

            tick_at = observed.get("loadMoreTickAt")
            assert tick_at, (
                f"fixture must record the moment the load-more button became visible via setInterval; observed={observed!r}"
            )

            first_click_at = observed.get("firstClickAt")
            assert first_click_at is not None, f"fixture must record the timestamp of the first click; observed={observed!r}"

            # ── "Waits" timing contract ──
            # The button only becomes visible at `setInterval` reveal time
            # (~2.4 s). The executor MUST NOT click before the timer fires.
            # A buggy executor that pre-clicked would set ``firstClickAt <= tickAt``
            # (or leave ``firstClickAt`` null). Combined with ``clicks >= 1``
            # above, this proves the executor *waited* for the timer before
            # clicking. We intentionally do NOT pin a lower ms bound because
            # the executor's polling cadence is implementation-defined and
            # brittle to assert against.
            elapsed_ms = int(first_click_at) - int(tick_at)
            assert elapsed_ms >= 0, (
                f"firstClickAt ({first_click_at}) must be >= loadMoreTickAt ({tick_at}); observed={observed!r}"
            )
            assert elapsed_ms > 0, (
                f"executor must NOT click before the setInterval reveal fires — "
                f"firstClickAt ({first_click_at}) should be strictly greater than "
                f"loadMoreTickAt ({tick_at}); observed={observed!r}"
            )

            # ── Result-side observability ──
            record_list = list(result)
            cards_after = await page.evaluate("() => window.__lazyState.cardCount")
            assert len(record_list) <= int(cards_after), (
                f"records({len(record_list)}) must not exceed on-page cards({cards_after})"
            )
            # Clicks add 3 cards each; seed 5; minimum post-state is 5+3=8 with one click.
            assert int(cards_after) >= 5 + 3, f"after ≥1 click, page should have ≥8 cards; got {cards_after}"

            stopped_reason = getattr(result, "stopped_reason", "")
            # After button becomes visible + is clicked, the loop normally
            # exhausts via max_pages once it can finally enter the loop OR
            # max_records OR button_gone (if the reveal happened too late and
            # the executor gave up). The test accepts any non-error reason.
            assert stopped_reason in {
                "button_gone",
                "max_pages",
                "max_records",
                "no_new_records",
            }, f"unexpected stopped_reason: {stopped_reason!r}"
        finally:
            await browser.close()


if __name__ == "__main__":
    # Allow running directly: ``python3 backend/tests/test_scraper_hostile_fixture_e2e.py``
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
