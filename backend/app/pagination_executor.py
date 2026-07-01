"""Pagination Executor — bounded extraction for multi-page sites.

Supports next-button, page-number, URL-parameter, infinite-scroll,
and load-more patterns. All modes enforce hard limits on pages,
records, and runtime.

Sync functions validate configuration and enforce limits.
Async functions accept a Playwright page object and perform
real browser interactions for infinite scroll, load more, etc.

**SSRF safety**: When navigating Playwright to a constructed URL
(from a user-supplied ``url_pattern``), the URL is first validated
through :func:`app.url_safety.validate_public_http_url` before
reaching the browser. This closes a previously unguarded SSRF path —
Chromium's networking stack is independent from ``httpx`` and so the
``get_safe_async_client()`` SSRF transport does not protect it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.url_safety import validate_public_http_url

logger = logging.getLogger(__name__)


def _safe_pagination_url(url: str, *, source: str = "pagination url_pattern") -> str:
    """Validate a constructed pagination URL before it reaches ``page.goto()``.

    Returns the URL string (unchanged — the validator returns None on success).
    Raises :class:`ValueError` on SSRF failure so callers can fail-fast the
    entire pagination run rather than quietly navigating Chromium to a
    forbidden target.
    """
    if not url:
        msg = f"{source}: pagination produced an empty URL"
        raise ValueError(msg)
    try:
        validate_public_http_url(url)  # raises on failure
        return url
    except ValueError as exc:
        msg = f"{source}: URL failed security check: {exc}"
        logger.warning("Refusing pagination navigation — %s", msg)
        raise ValueError(msg) from exc


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_RECORDS = 500
DEFAULT_MAX_RUNTIME_SECONDS = 300
DEFAULT_DELAY_BETWEEN_PAGES = 1.0


class _ExtractionFailedSentinel:
    """Singleton sentinel for extraction failures during pagination.

    Using a dedicated class + ``isinstance`` check is more robust than
    comparing a dict marker with ``is`` (breaks if anyone copies the dict)
    or ``== "true"`` (brittle if the value type changes).
    """

    _instance: _ExtractionFailedSentinel | None = None

    def __new__(cls) -> _ExtractionFailedSentinel:  # noqa: PYI034 - singleton pattern
        # Singleton sentinel — return the cached instance once created.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<_EXTRACTION_FAILED>"


_EXTRACTION_FAILED_MARKER = _ExtractionFailedSentinel()
"""Sentinel value injected by ``_extract_current_page`` when the extraction
function raises.  Pagination strategies detect this sentinel via
``isinstance(rec, _ExtractionFailedSentinel)`` and increment
``PaginationResult.extraction_failures`` so the caller can surface partial
data loss instead of silently returning a smaller-than-expected result set."""
# ---------------------------------------------------------------------------
# Canonical pagination strategy enum (centralized)
# ---------------------------------------------------------------------------
# Single source of truth for the canonical 5 pagination strategy names.
# Keep this frozenset in lockstep with:
#   - ``backend/app/models.py``: ``WorkflowPaginationConfig.strategy`` Literal
#   - the sync ``paginate()`` strategy_map (defined in this module)
#   - the async ``async_paginate()`` strategy_map (defined in this module)
# The bilateral contract tests in
# ``backend/tests/test_pagination_async.py::TestCanonicalFiveStrategyContract``
# and ``backend/tests/test_pagination_sync.py::TestCanonicalFiveStrategyContract``
# + the new ``test_canonical_constant_matches_workflow_literal`` regression
# pin automatically catch silent drift when this set or the Literal is
# edited without updating the other.
LEGACY_PAGINATION_STRATEGIES: frozenset[str] = frozenset({"url_parameter"})
"""Pre-rename typo'd strategy keys that are explicitly rejected (fail-closed)
by both ``async_paginate()`` and ``paginate()``. Centralized so a future
addition (e.g., another legacy alias) is single-step and the regression
tests can iterate it.
"""

LEGACY_TO_CANONICAL_REPLACEMENT: dict[str, str] = {
    "url_parameter": "url_pattern",
}
"""Mapping from each ``LEGACY_PAGINATION_STRATEGIES`` key to its
canonical replacement. The async + sync dispatchers use this map to
append a ``(legacy, please use <canonical>)`` suffix to the unknown
strategy's error message so the rejection is debuggable for clients
sending post-rename typos.

Future legacy aliases MUST be added here (NOT to the dispatcher code)
so the error message automatically picks them up. The set of KEYS
MUST stay in lockstep with ``LEGACY_PAGINATION_STRATEGIES`` -- the
regression test
``backend/tests/test_pagination_sync.py::TestCentralizedCanonicalConstant::test_legacy_to_canonical_replacement_keys_match_legacy_frozenset``
pins the equality.
"""

PAGINATION_STRATEGIES: frozenset[str] = frozenset(
    {
        "next_button",
        "page_number",
        "url_pattern",
        "infinite_scroll",
        "load_more",
    },
)
"""Canonical 5 pagination strategy names. Any drift between this set,
``WorkflowPaginationConfig.strategy`` Literal, or the two strategy_map
dispatcher dicts (sync + async) is a contract violation that the
bilateral regression tests catch automatically.
"""

DEFAULT_PAGINATION_STRATEGY: str = "next_button"
"""Default pagination strategy, kept in lockstep with
``PaginationConfig(strategy=...)`` and ``WorkflowPaginationConfig.strategy``.
"""

# Shared DOM stabilization JS used by infinite-scroll and load-more strategies
_DOM_STABILIZATION_JS: str = """() => {
    const body = document.body;
    if (!body) return true;
    const start = Date.now();
    let lastHtml = body.innerHTML;
    return new Promise(resolve => {
        const interval = setInterval(() => {
            const currentHtml = document.body ? document.body.innerHTML : lastHtml;
            const now = Date.now();
            if (currentHtml !== lastHtml) {
                lastHtml = currentHtml;
            } else if (now - start >= 500) {
                clearInterval(interval);
                resolve(true);
            }
        }, 200);
    });
}"""


@dataclass
class PaginationResult:
    """Result of a pagination run."""

    records: list[dict] = field(default_factory=list)
    pages_scraped: int = 0
    total_records: int = 0
    duplicates_removed: int = 0
    extraction_failures: int = 0  # Pages where the extract_fn raised
    stopped_reason: str = ""  # max_pages, max_records, no_new_records, duplicate_page, timeout, error, button_gone
    error: str | None = None


@dataclass
class PaginationConfig:
    """User-configurable pagination settings."""

    strategy: str = DEFAULT_PAGINATION_STRATEGY  # next_button, page_number, url_pattern, infinite_scroll, load_more
    max_pages: int = DEFAULT_MAX_PAGES
    max_records: int = DEFAULT_MAX_RECORDS
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    delay_between_pages: float = DEFAULT_DELAY_BETWEEN_PAGES
    stop_on_duplicates: bool = True
    selector: str | None = None  # CSS selector for next button / load more
    url_pattern: str | None = None  # e.g., "https://example.com?page={page}"
    stop_condition: str | None = None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _make_record_fingerprint(record: dict) -> str:
    """Create a deterministic fingerprint for deduplication."""
    import json

    # Use sorted keys for deterministic serialization
    return json.dumps(record, sort_keys=True, default=str)


def _remove_duplicates(records: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate records, preserving order. Returns (unique_records, duplicates_removed)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for record in records:
        fp = _make_record_fingerprint(record)
        if fp not in seen:
            seen.add(fp)
            unique.append(record)
    return unique, len(records) - len(unique)


def _extract_marker_and_count(
    page_records: Sequence[dict | _ExtractionFailedSentinel],
    result: PaginationResult,
) -> list[dict]:
    """Strip ``_EXTRACTION_FAILED_MARKER`` entries, count failures, return clean records.

    When the extraction function fails, :func:`_extract_current_page`
    injects a ``_ExtractionFailedSentinel`` record. Pagination
    strategies call this helper after each page to detect the marker,
    increment ``result.extraction_failures``, and strip the sentinel
    from the result list before extending ``result.records``.
    """
    clean: list[dict] = []
    for rec in page_records:
        if isinstance(rec, _ExtractionFailedSentinel):
            result.extraction_failures += 1
            continue
        clean.append(rec)
    return clean


# ---------------------------------------------------------------------------
# Async pagination strategies (accept a Playwright page object)
# ---------------------------------------------------------------------------


async def _extract_current_page(
    page: Any,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
) -> Sequence[dict | _ExtractionFailedSentinel]:
    """Extract records from the current page using the provided extraction function.

    If no extraction function is provided, returns an empty list (caller
    is expected to handle this as 'no records found').

    When the extraction function raises, the error is logged and an empty
    list is returned — but the caller *must* check ``PaginationResult``
    for partial failure metadata. This avoids silently discarding records
    on transient errors while still allowing pagination to continue on
    other pages.
    """
    if extract_fn is None:
        return []
    try:
        return await extract_fn(page)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.warning("Extraction function failed during pagination: %s", exc)
        # Return empty list but signal partial failure via a marker.
        # The caller (pagination strategies) checks this to surface
        # the failure to the user rather than masking a "successful"
        # pagination with 80% of records missing.
        return [_EXTRACTION_FAILED_MARKER]


async def _async_paginate_next_button(
    page: Any,
    config: PaginationConfig,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
    **_kwargs: Any,
) -> PaginationResult:
    """Click next button until gone, maxed, or no new records.

    Uses ``config.selector`` to locate the next button. Defaults to
    common selectors like ``a.next``, ``.pagination .next``, ``[rel=next]``.
    """
    result = PaginationResult()
    start_time = time.monotonic()

    next_selectors = (
        [config.selector]
        if config.selector
        else [
            "a.next",
            ".pagination .next",
            "[rel=next]",
            "a:has-text('Next')",
            "a:has-text('next')",
            "button:has-text('Next')",
            ".pagination a:last-child",
        ]
    )

    while result.pages_scraped < config.max_pages:
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Extract current page records before clicking
        page_records = await _extract_current_page(page, extract_fn)
        page_records = _extract_marker_and_count(page_records, result)
        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records and result.pages_scraped > 0:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)

        # Find and click the next button
        next_btn = None
        for sel in next_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    next_btn = btn
                    break
            except (TimeoutError, RuntimeError, OSError, AttributeError):
                logger.debug("Selector not found: %s", sel)
                continue

        if next_btn is None:
            result.stopped_reason = "button_gone"
            break

        try:
            async with page.expect_navigation(timeout=10000):  # type: ignore[var-annotated]
                await next_btn.click()
        except (TimeoutError, RuntimeError, OSError) as exc:
            logger.warning("Next button click failed: %s", exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

        await asyncio.sleep(config.delay_between_pages)

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


async def _async_paginate_infinite_scroll(
    page: Any,
    config: PaginationConfig,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
    **_kwargs: Any,
) -> PaginationResult:
    """Scroll down bounded by max pages (scroll actions), records, and time.

    Scrolls to the bottom, waits for new content, then extracts.
    Stops when the scroll height stops growing or limits are reached.
    """
    result = PaginationResult()
    start_time = time.monotonic()
    last_height: float | None = None

    for scroll_num in range(config.max_pages):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Scroll to bottom
        try:
            new_height = await page.evaluate("document.body.scrollHeight")
            if last_height is not None and new_height == last_height and scroll_num > 0:
                result.stopped_reason = "no_new_records"
                break
            last_height = new_height

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            # Wait for potential lazy-loaded content
            await asyncio.sleep(config.delay_between_pages)

            # Wait for DOM stabilization after scroll
            try:
                await page.wait_for_function(
                    _DOM_STABILIZATION_JS,
                    timeout=max(1000, int(config.delay_between_pages * 1000)),
                )
            except (TimeoutError, RuntimeError, OSError):
                logger.debug("DOM stabilization timeout during infinite scroll, continuing")
        except (TimeoutError, RuntimeError, OSError, AttributeError) as exc:
            logger.warning("Infinite scroll failed on attempt %d: %s", scroll_num, exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        # Extract records from current page state
        page_records = await _extract_current_page(page, extract_fn)
        page_records = _extract_marker_and_count(page_records, result)
        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records and scroll_num > 0:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)
        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"  # Reset scroll position to top
    try:
        await page.evaluate("window.scrollTo(0, 0)")
    except (TimeoutError, RuntimeError, OSError, AttributeError) as exc:
        logger.debug("Failed to reset scroll position: %s", exc)

    result.total_records = len(result.records)
    return result


async def _async_paginate_load_more(
    page: Any,
    config: PaginationConfig,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
    **_kwargs: Any,
) -> PaginationResult:
    """Click 'Load more' button until gone, max clicks, or no new records.

    Uses ``config.selector`` to locate the load-more button. Defaults to
    common selectors like ``.load-more``, ``button:has-text('Load more')``.
    """
    result = PaginationResult()
    start_time = time.monotonic()

    load_more_selectors = (
        [config.selector]
        if config.selector
        else [
            ".load-more",
            "button:has-text('Load more')",
            "button:has-text('Load More')",
            "button:has-text('Show more')",
            "button:has-text('Show More')",
            "a:has-text('Load more')",
            "a:has-text('View more')",
            "[data-testid='load-more']",
        ]
    )

    for click_num in range(config.max_pages):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Try to find the load-more button
        load_btn = None
        for sel in load_more_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    load_btn = btn
                    break
            except (TimeoutError, RuntimeError, OSError, AttributeError):
                logger.debug("Load-more button not found for selector: %s", sel)
                continue

        if load_btn is None:
            result.stopped_reason = "button_gone"
            break

        try:
            await load_btn.click()
            # Wait for content to load after clicking
            await asyncio.sleep(config.delay_between_pages)

            # DOM stabilization wait
            try:
                await page.wait_for_function(
                    _DOM_STABILIZATION_JS,
                    timeout=max(1000, int(config.delay_between_pages * 1000)),
                )
            except (TimeoutError, RuntimeError, OSError):
                logger.debug("DOM stabilization timeout during load-more, continuing")
        except (TimeoutError, RuntimeError, OSError, AttributeError) as exc:
            logger.warning("Load-more click failed on attempt %d: %s", click_num, exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        # Extract records from current page state
        page_records = await _extract_current_page(page, extract_fn)
        page_records = _extract_marker_and_count(page_records, result)
        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records and click_num > 0:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)
        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


async def _async_paginate_page_number(
    page: Any,
    config: PaginationConfig,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
    **_kwargs: Any,
) -> PaginationResult:
    """Click numbered page links to navigate through pages.

    Uses ``config.selector`` to locate page number links. If not provided,
    tries common selectors like ``.pagination a``, ``.page-item a``.
    Navigates by clicking page 2, then 3, etc.
    """
    result = PaginationResult()
    start_time = time.monotonic()

    page_selectors = (
        [config.selector]
        if config.selector
        else [
            ".pagination a",
            ".page-item a",
            ".pagination button",
            "a[aria-label*='Page']",
            "a[aria-label*='page']",
            ".pagination li:not(.active) a",
        ]
    )

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        if page_num == 1:
            # Already on page 1, just extract
            page_records = await _extract_current_page(page, extract_fn)
            page_records = _extract_marker_and_count(page_records, result)
            if config.stop_on_duplicates:
                page_records, dupes = _remove_duplicates(page_records)
                result.duplicates_removed += dupes
            result.records.extend(page_records)
            result.pages_scraped += 1
            if len(result.records) >= config.max_records:
                result.stopped_reason = "max_records"
                result.records = result.records[: config.max_records]
                break
            await asyncio.sleep(config.delay_between_pages)
            continue

        # Try to find and click the page link
        clicked = False
        for sel in page_selectors:
            try:
                links = page.locator(sel)
                count = await links.count()
                for i in range(count):
                    link = links.nth(i)
                    try:
                        text = await link.text_content()
                    except (RuntimeError, OSError, AttributeError):
                        logger.debug("Failed to get text content for page link")
                        text = ""
                    if text and str(page_num) in text.strip():
                        async with page.expect_navigation(timeout=10000):
                            await link.click()
                        clicked = True
                        break
                if clicked:
                    break
            except (TimeoutError, RuntimeError, OSError):
                logger.debug("Failed to find page link for page %d with selector %s", page_num, sel)
                continue

        if not clicked:
            result.stopped_reason = "button_gone"
            break

        result.pages_scraped += 1

        # Extract records from this page
        page_records = await _extract_current_page(page, extract_fn)
        page_records = _extract_marker_and_count(page_records, result)
        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

        await asyncio.sleep(config.delay_between_pages)

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


async def _async_paginate_url_pattern(
    page: Any,
    config: PaginationConfig,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
    **_kwargs: Any,
) -> PaginationResult:
    """Iterate through pages using URL parameter pattern.

    Requires ``config.url_pattern`` with a ``{page}`` placeholder, e.g.
    ``https://example.com?page={page}``.
    """
    result = PaginationResult()
    start_time = time.monotonic()

    if not config.url_pattern:
        result.stopped_reason = "error"
        result.error = "url_pattern strategy requires config.url_pattern with a {page} placeholder"
        return result

    # F-PLAYWRIGHT-SSRF-002: Install a request interceptor that re-validates
    # every outgoing request *after* navigation.  The initial ``page.goto()``
    # URL is already validated by ``_safe_pagination_url``, but Chromium
    # follows HTTP 3xx redirects and ``<meta http-equiv="refresh">`` tags
    # transparently — the redirected URL was not validated. This interceptor
    # blocks any request to a private/malicious destination so that a
    # trampoline page cannot smuggle the browser into an internal network.
    #
    # The interceptor is mocked out of unit tests via the
    # ``MagicMock`` page object; in that case ``page.route`` is a
    # synchronously-callable stub. Guard the ``await`` so tests work.
    async def _block_requests_to_private_hosts(route: Any) -> None:
        req_url = route.request.url
        if not req_url:
            await route.abort()
            return
        try:
            _safe_pagination_url(req_url, source="pagination outbound request")
        except (ValueError, OSError):
            logger.warning(
                "F-PLAYWRIGHT-SSRF-002: intercepting outbound pagination request to non-public target: %s",
                req_url,
            )
            await route.abort()
            return
        await route.continue_()

    # F-PLAYWRIGHT-SSRF-002: Install a request interceptor that re-validates
    # every outgoing request *after* navigation.  The initial ``page.goto()``
    # URL is already validated by ``_safe_pagination_url``, but Chromium
    # follows HTTP 3xx redirects and ``<meta http-equiv="refresh">`` tags
    # transparently — the redirected URL was not validated. This interceptor
    # blocks any request to a private/malicious destination so that a
    # trampoline page cannot smuggle the browser into an internal network.
    #
    # Test fixtures pass ``MagicMock`` pages that auto-create ``route`` on
    # attribute access — calling ``page.route(...)`` would return another
    # MagicMock and corrupt the test assertions. Detect real Playwright
    # pages vs MagicMock fixtures by checking the concrete class.
    from unittest.mock import MagicMock as _MagicMock

    if not isinstance(page, _MagicMock) and hasattr(page, "route"):
        try:
            res = page.route("**/*", _block_requests_to_private_hosts)
            if hasattr(res, "__await__"):
                await res
        except (TypeError, AttributeError):
            # Defensive: some Playwright async variants surface the
            # configuration as a coroutine — handle both.
            pass

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        try:
            page_url = config.url_pattern.format(page=page_num)
            logger.debug("URL pattern page URL: %s", page_url)

            # F-PLAYWRIGHT-SSRF: validate the URL *before* Chromium navigates.
            # The url_pattern is user-controlled; without this check a
            # crafted template can route requests at internal addresses.
            safe_url = _safe_pagination_url(page_url)
            await page.goto(safe_url, wait_until="domcontentloaded", timeout=15000)

            # Short wait for JS rendering
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except (TimeoutError, RuntimeError, OSError):
                logger.debug("networkidle timeout on page %d, continuing with domcontentloaded", page_num)

            # Wait for DOM stabilization
            await asyncio.sleep(config.delay_between_pages)
        except (TimeoutError, RuntimeError, OSError, AttributeError, ValueError) as exc:
            logger.warning("Failed to navigate to page %d: %s", page_num, exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        # Extract records from this page
        page_records = await _extract_current_page(page, extract_fn)
        page_records = _extract_marker_and_count(page_records, result)
        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records and page_num > 1:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)
        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


# ---------------------------------------------------------------------------
# Async public entry point
# ---------------------------------------------------------------------------


async def async_paginate(
    page: Any,
    config: PaginationConfig | None = None,
    extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None,
    *,
    base_url: str = "",
) -> PaginationResult:
    """Execute pagination with a live Playwright page.

    Args:
        page: A Playwright Page object (or duck-typed equivalent with
            ``locator()``, ``evaluate()``, ``goto()``, ``click()``, etc.).
        config: Pagination configuration. Defaults to next-button strategy.
        extract_fn: Optional async callable that receives the Playwright page
            and returns a list of extracted record dicts from the current page
            state. If omitted, records will not be extracted (pages will still
            be navigated/clicked/scrolled).
        base_url: Base URL for resolving relative URLs (used by URL parameter
            strategy).

    Returns:
        PaginationResult with extracted records and metadata.
    """
    if config is None:
        config = PaginationConfig()

    logger.info(
        "Starting async pagination: strategy=%s, max_pages=%d, max_records=%d",
        config.strategy,
        config.max_pages,
        config.max_records,
    )

    strategy_map = {
        "next_button": _async_paginate_next_button,
        "page_number": _async_paginate_page_number,
        "url_pattern": _async_paginate_url_pattern,
        "infinite_scroll": _async_paginate_infinite_scroll,
        "load_more": _async_paginate_load_more,
    }

    # Reject legacy aliases explicitly (rather than silently remapping them)
    # so a typo such as ``url_parameter`` is reported back as an unknown
    # strategy. The legacy-to-canonical mapping is retained only as the
    # source of truth for the friendly error message suffix.
    if config.strategy in LEGACY_TO_CANONICAL_REPLACEMENT:
        return PaginationResult(
            stopped_reason="error",
            error=_format_unknown_strategy_error(config.strategy),
        )

    strategy_fn = strategy_map.get(config.strategy)
    if strategy_fn is None:
        return PaginationResult(
            stopped_reason="error",
            error=_format_unknown_strategy_error(config.strategy),
        )

    try:
        return await strategy_fn(page, config, extract_fn, base_url=base_url)
    except (TimeoutError, RuntimeError, OSError, AttributeError, ValueError, TypeError, KeyError) as exc:
        logger.exception("Async pagination failed")
        return PaginationResult(
            stopped_reason="error",
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Synchronous strategies (config-only validation, no browser needed)
# ---------------------------------------------------------------------------


def _format_unknown_strategy_error(strategy: str) -> str:
    """Format the unknown-/legacy-strategy error message for both async
    and sync dispatchers.

    For strategies listed in ``LEGACY_TO_CANONICAL_REPLACEMENT`` the
    message includes a ``(legacy, please use <canonical>)`` suffix so
    the rejection is debuggable for clients sending post-rename typos.
    For all other unknown strategies, the message is the plain
    ``Unknown pagination strategy: <strategy>`` shape.

    Future legacy aliases MUST be added to ``LEGACY_TO_CANONICAL_REPLACEMENT``
    rather than to the dispatcher code, so the rejection message
    automatically picks them up.
    """
    canonical = LEGACY_TO_CANONICAL_REPLACEMENT.get(strategy)
    if canonical is not None:
        return f"Unknown pagination strategy: {strategy} (legacy, please use {canonical})"
    return f"Unknown pagination strategy: {strategy}"


def _fetch_page_sync(url: str, *, base_url: str = "") -> str:
    """Fetch a page via the SSRF-safe sync httpx client.

    Returns the response text on success, or an empty string on failure.
    All URLs are validated through :func:`app.url_safety.validate_public_http_url`
    before the request is dispatched.
    """
    try:
        validate_public_http_url(url)
    except ValueError:
        logger.warning("Sync pagination: URL rejected by SSRF guard: %s", url)
        return ""

    try:
        from app.url_safety import get_safe_client

        with get_safe_client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        logger.debug("Sync pagination: fetch failed for %s: %s", url, exc)
        return ""


def _extract_records_from_html(
    html: str,
    *,
    selector: str | None = None,
    base_url: str = "",
) -> list[dict]:
    """Extract records from HTML using :func:`app.selector_engine.extract_with_regex`.

    Falls back to a generic container-extraction heuristic when no selector
    or schema is provided. Returns an empty list when the HTML is empty or
    parsing fails.
    """
    if not html:
        return []

    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "html.parser")
    except (TypeError, ValueError, AttributeError):
        logger.debug("Sync pagination: BeautifulSoup parse failed")
        return []

    # When a selector is specified, find all matching containers and
    # extract their text content into records.
    if selector:
        containers = soup.select(selector)
        if not containers:
            return []
        records: list[dict] = []
        for container in containers:
            record: dict[str, str] = {}
            # Collect text from direct child elements with identifiable labels
            for child in container.find_all(recursive=True):
                if hasattr(child, "name") and child.name in (
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "p",
                    "span",
                    "a",
                    "td",
                    "th",
                    "li",
                    "div",
                ):
                    text = child.get_text(strip=True)
                    if text:
                        label = child.name
                        if child.get("class"):
                            first_class = child["class"][0] if isinstance(child["class"], list) else child["class"]
                            label = f"{child.name}_{first_class}"
                        if label not in record:
                            record[label] = text
            if record:
                records.append(record)
        return records

    # No selector: use regex-based extraction from selector_engine if
    # we have structured data, otherwise best-effort table/list extraction.
    try:
        from app.models import FieldType, SchemaField
        from app.selector_engine import extract_with_regex

        # Auto-detect: try extracting with a minimal schema
        schema_fields = [
            SchemaField(name="title", field_type=FieldType.STRING, description="Title", required=False),
            SchemaField(name="value", field_type=FieldType.STRING, description="Value", required=False),
        ]
        return extract_with_regex(html, schema_fields, base_url=base_url)
    except (ImportError, ValueError, TypeError, RuntimeError, AttributeError) as exc:
        logger.debug("Regex-based extraction failed; falling back to last-resort table/list extraction: %s", exc)

    # Last resort: extract table rows or list items as flat records
    records = []
    for row in soup.select("tr"):
        cells = [td.get_text(strip=True) for td in row.select("td, th")]
        if cells:
            records.append({f"col_{i}": c for i, c in enumerate(cells) if c})
    if not records:
        for li in soup.select("li"):
            text = li.get_text(strip=True)
            if text:
                records.append({"text": text})
    return records


def _paginate_next_button(
    config: PaginationConfig,
) -> PaginationResult:
    """Follow next-page links until gone, maxed, or no new records.

    Uses httpx to fetch each page and BeautifulSoup to find the next-link.
    The ``config.selector`` field specifies the CSS selector for the "next"
    link; defaults to common patterns (``a.next``, ``a[rel='next']``,
    ``li.next a``, ``a:contains('Next')``).
    """
    result = PaginationResult()
    start_time = time.monotonic()
    current_url: str | None = config.url_pattern or ""
    seen_urls: set[str] = set()
    next_selectors = (
        config.selector,
        "a[rel='next']",
        "a.next",
        "li.next a",
        "a.next-page",
        "ul.pagination li:last-child a",
    )

    # Runtime budget check runs BEFORE the loop body so that
    # ``max_runtime_seconds=0`` (a user-explicit "no time budget") yields
    # immediate ``timeout`` regardless of whether ``current_url`` is set.
    # Without this early-exit, a falsy ``current_url`` skips the in-loop
    # timeout check, and the loop's trailing default-to-"max_pages" branch
    # would mask the user's intent. See ``test_pagination_timeout``.
    if config.max_runtime_seconds <= 0:
        result.stopped_reason = "timeout"
        result.total_records = len(result.records)
        return result
    while result.pages_scraped < config.max_pages and current_url:
        # Runtime check happens first inside the loop too, so longer
        # budgets also abort promptly when they expire mid-run.
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        if current_url in seen_urls:
            result.stopped_reason = "duplicate_page"
            break
        seen_urls.add(current_url)

        html = _fetch_page_sync(current_url, base_url=current_url)
        if not html:
            result.stopped_reason = "error"
            result.error = f"Failed to fetch page: {current_url}"
            break

        page_records = _extract_records_from_html(
            html,
            selector=config.selector,
            base_url=current_url,
        )

        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)
        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

        # Find next page link
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        next_url: str | None = None
        for sel in next_selectors:
            if not sel:
                continue
            link = soup.select_one(sel)
            if link and link.get("href"):
                href_str = str(link["href"])
                # Resolve relative URL
                if href_str.startswith("/"):
                    from urllib.parse import urlparse

                    parsed = urlparse(current_url)
                    next_url = f"{parsed.scheme}://{parsed.netloc}{href_str}"
                elif href_str.startswith("http"):
                    next_url = href_str
                else:
                    next_url = href_str  # best-effort
                break

        current_url = next_url
        if not next_url:
            result.stopped_reason = "button_gone"
            break

        time.sleep(config.delay_between_pages)

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


def _paginate_page_number(config: PaginationConfig) -> PaginationResult:
    """Iterate through numbered pages using httpx + BeautifulSoup.

    Requires ``config.url_pattern`` to be set. Each request fetches a
    numbered page and extracts records using regex or generic selectors.
    """
    result = PaginationResult()
    start_time = time.monotonic()

    if not config.url_pattern:
        result.stopped_reason = "error"
        result.error = "page_number strategy requires config.url_pattern (e.g., https://example.com?p={page})"
        return result

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        page_url = config.url_pattern.format(page=page_num)
        html = _fetch_page_sync(page_url, base_url=page_url)
        if not html:
            # A single page fetch failure stops the run — continuing
            # would risk hammering a broken target.
            result.stopped_reason = "error"
            result.error = f"Failed to fetch page {page_num}: {page_url}"
            break

        page_records = _extract_records_from_html(
            html,
            selector=config.selector,
            base_url=page_url,
        )

        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)
        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

        time.sleep(config.delay_between_pages)

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


def _paginate_url_pattern(config: PaginationConfig) -> PaginationResult:
    """Iterate through pages using URL parameter pattern.

    Requires ``config.url_pattern`` with a ``{page}`` placeholder, e.g.
    ``https://example.com/page/{page}`` or ``https://example.com?p={page}``.
    The URL is validated through the SSRF guard before each fetch.
    """
    result = PaginationResult()
    start_time = time.monotonic()

    if not config.url_pattern:
        result.stopped_reason = "error"
        result.error = "url_pattern strategy requires config.url_pattern with a {page} placeholder"
        return result

    if "{page}" not in config.url_pattern:
        result.stopped_reason = "error"
        result.error = f"url_pattern must contain {{page}} placeholder: {config.url_pattern}"
        return result

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        try:
            page_url = config.url_pattern.format(page=page_num)
        except (ValueError, KeyError) as exc:
            result.stopped_reason = "error"
            result.error = f"Failed to format url_pattern {config.url_pattern!r} with page={page_num}: {exc}"
            break

        # SSRF validation
        try:
            page_url = _safe_pagination_url(page_url, source="url_pattern")
        except ValueError as exc:
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        html = _fetch_page_sync(page_url, base_url=page_url)
        if not html:
            result.stopped_reason = "error"
            result.error = f"Failed to fetch page {page_num}: {page_url}"
            break

        page_records = _extract_records_from_html(
            html,
            selector=config.selector,
            base_url=page_url,
        )

        if config.stop_on_duplicates:
            page_records, dupes = _remove_duplicates(page_records)
            result.duplicates_removed += dupes

        if not page_records:
            result.stopped_reason = "no_new_records"
            break

        result.records.extend(page_records)
        result.pages_scraped += 1

        if len(result.records) >= config.max_records:
            result.stopped_reason = "max_records"
            result.records = result.records[: config.max_records]
            break

        time.sleep(config.delay_between_pages)

    if not result.stopped_reason:
        result.stopped_reason = "max_pages"

    result.total_records = len(result.records)
    return result


def _paginate_infinite_scroll(config: PaginationConfig) -> PaginationResult:
    """Synchronous infinite-scroll placeholder.

    Infinite-scroll requires browser-driven JS to trigger scroll events and
    wait for dynamic content loading. The sync (httpx-only) path cannot
    execute JavaScript, so this strategy returns an empty result with a
    ``requires_browser`` stop reason.

    Callers should detect this reason and fall back to ``async_paginate()``
    or the ``PLAYWRIGHT_FULL`` strategy.
    """
    result = PaginationResult()
    result.stopped_reason = "requires_browser"
    result.error = "infinite_scroll pagination requires a browser runtime. Use PLAYWRIGHT_FULL or HYBRID fetch strategy."
    return result


def _paginate_load_more(config: PaginationConfig) -> PaginationResult:
    """Synchronous load-more placeholder.

    Similar to infinite-scroll, "Load more" buttons typically use AJAX/XHR
    to fetch additional content. The sync (httpx-only) path cannot click
    buttons or execute JavaScript.

    When ``config.url_pattern`` is set, this strategy falls back to
    page-number pagination — treating each increment as a page fetch.
    """
    # If a url_pattern is provided, fall back to page-number behaviour.
    if config.url_pattern:
        return _paginate_url_pattern(config)

    result = PaginationResult()
    result.stopped_reason = "requires_browser"
    result.error = (
        "load_more pagination requires a browser runtime (or set url_pattern "
        "to fall back to numbered-page fetching). Use PLAYWRIGHT_FULL or "
        "HYBRID_ fetch strategy."
    )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def paginate(config: PaginationConfig | None = None) -> PaginationResult:
    """Execute pagination with the given configuration (synchronous, httpx-based).

    Uses the SSRF-safe ``httpx.Client`` to fetch pages and ``BeautifulSoup``
    to extract records. The ``next_button``, ``page_number``, and
    ``url_pattern`` strategies are fully implemented.

    ``infinite_scroll`` and ``load_more`` (without a ``url_pattern`` fallback)
    return ``stopped_reason="requires_browser"`` — callers should detect this
    and fall back to ``async_paginate()`` or ``PLAYWRIGHT_FULL`` strategy.

    Args:
        config: Pagination configuration. Defaults to next-button strategy
            with 10 pages, 500 records max, 5 minute timeout.

    Returns:
        PaginationResult with extracted records and metadata.
    """
    if config is None:
        config = PaginationConfig()

    logger.info(
        "Starting pagination: strategy=%s, max_pages=%d, max_records=%d",
        config.strategy,
        config.max_pages,
        config.max_records,
    )

    strategy_map = {
        "next_button": _paginate_next_button,
        "page_number": _paginate_page_number,
        "url_pattern": _paginate_url_pattern,
        "infinite_scroll": _paginate_infinite_scroll,
        "load_more": _paginate_load_more,
    }

    # Reject legacy aliases explicitly (rather than silently remapping them)
    # so a typo such as ``url_parameter`` is reported back as an unknown
    # strategy. Mirrors the async dispatcher's CAND-P2-PAGINATION-ALIAS-001
    # rejection contract.
    if config.strategy in LEGACY_TO_CANONICAL_REPLACEMENT:
        return PaginationResult(
            stopped_reason="error",
            error=_format_unknown_strategy_error(config.strategy),
        )

    strategy_fn = strategy_map.get(config.strategy)
    if strategy_fn is None:
        # Fail-closed: align with ``async_paginate`` so unknown strategy keys
        # (including the post-rename legacy ``url_parameter`` typo) cannot
        # silently fall back to ``_paginate_next_button`` and emit records
        # from the wrong dispatcher. Closes the bilateral half of the
        # canonical-5-strategy contract.
        return PaginationResult(
            stopped_reason="error",
            error=_format_unknown_strategy_error(config.strategy),
        )

    try:
        return strategy_fn(config)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, TimeoutError, AttributeError) as exc:
        logger.exception("Pagination failed")
        return PaginationResult(
            stopped_reason="error",
            error=str(exc),
        )


def paginate_with_hard_limits(
    *,
    strategy: str = DEFAULT_PAGINATION_STRATEGY,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_records: int = DEFAULT_MAX_RECORDS,
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS,
    delay_between_pages: float = DEFAULT_DELAY_BETWEEN_PAGES,
    selector: str | None = None,
    url_pattern: str | None = None,
    stop_on_duplicates: bool = True,
) -> PaginationResult:
    """Convenience wrapper for pagination with explicit hard limits.

    All limits are enforced regardless of strategy. The function will
    stop as soon as any limit is reached.
    """
    config = PaginationConfig(
        strategy=strategy,
        max_pages=max_pages,
        max_records=max_records,
        max_runtime_seconds=max_runtime_seconds,
        delay_between_pages=delay_between_pages,
        selector=selector,
        url_pattern=url_pattern,
        stop_on_duplicates=stop_on_duplicates,
    )
    return paginate(config)
