"""Pagination Executor — bounded extraction for multi-page sites.

Supports next-button, page-number, URL-parameter, infinite-scroll,
and load-more patterns. All modes enforce hard limits on pages,
records, and runtime.

Sync functions validate configuration and enforce limits.
Async functions accept a Playwright page object and perform
real browser interactions for infinite scroll, load more, etc.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_RECORDS = 500
DEFAULT_MAX_RUNTIME_SECONDS = 300
DEFAULT_DELAY_BETWEEN_PAGES = 1.0


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


# ---------------------------------------------------------------------------
# Async pagination strategies (accept a Playwright page object)
# ---------------------------------------------------------------------------


async def _extract_current_page(page: Any, extract_fn: Callable[[Any], Awaitable[list[dict]]] | None = None) -> list[dict]:
    """Extract records from the current page using the provided extraction function.

    If no extraction function is provided, returns an empty list (caller
    is expected to handle this as 'no records found').
    """
    if extract_fn is None:
        return []
    try:
        return await extract_fn(page)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.warning("Extraction function failed during pagination: %s", exc)
        return []


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
            except Exception:
                logger.debug("Selector not found: %s", sel)
                continue

        if next_btn is None:
            result.stopped_reason = "button_gone"
            break

        try:
            async with page.expect_navigation(timeout=10000):  # type: ignore[var-annotated]
                await next_btn.click()
        except Exception as exc:
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
            except Exception:
                logger.debug("DOM stabilization timeout during infinite scroll, continuing")
        except Exception as exc:
            logger.warning("Infinite scroll failed on attempt %d: %s", scroll_num, exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        # Extract records from current page state
        page_records = await _extract_current_page(page, extract_fn)
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
    except Exception as exc:
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
            except Exception:
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
            except Exception:
                logger.debug("DOM stabilization timeout during load-more, continuing")
        except Exception as exc:
            logger.warning("Load-more click failed on attempt %d: %s", click_num, exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        # Extract records from current page state
        page_records = await _extract_current_page(page, extract_fn)
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
                    except Exception:
                        logger.debug("Failed to get text content for page link")
                        text = ""
                    if text and str(page_num) in text.strip():
                        async with page.expect_navigation(timeout=10000):
                            await link.click()
                        clicked = True
                        break
                if clicked:
                    break
            except Exception:
                logger.debug("Failed to find page link for page %d with selector %s", page_num, sel)
                continue

        if not clicked:
            result.stopped_reason = "button_gone"
            break

        result.pages_scraped += 1

        # Extract records from this page
        page_records = await _extract_current_page(page, extract_fn)
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

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        try:
            page_url = config.url_pattern.format(page=page_num)
            logger.debug("URL pattern page URL: %s", page_url)

            await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)

            # Short wait for JS rendering
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                logger.debug("networkidle timeout on page %d, continuing with domcontentloaded", page_num)

            # Wait for DOM stabilization
            await asyncio.sleep(config.delay_between_pages)
        except Exception as exc:
            logger.warning("Failed to navigate to page %d: %s", page_num, exc)
            result.stopped_reason = "error"
            result.error = str(exc)
            break

        # Extract records from this page
        page_records = await _extract_current_page(page, extract_fn)
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

    strategy_fn = strategy_map.get(config.strategy)
    if strategy_fn is None:
        return PaginationResult(
            stopped_reason="error",
            error=_format_unknown_strategy_error(config.strategy),
        )

    try:
        return await strategy_fn(page, config, extract_fn, base_url=base_url)
    except Exception as exc:
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


def _extract_from_current_page() -> list[dict]:
    """Placeholder: would extract records from the current page DOM.

    In a full implementation, this would use the configured extraction
    schema and selector engine against the live page.
    """
    return []


def _paginate_next_button(
    config: PaginationConfig,
) -> PaginationResult:
    """Click next button until gone, maxed, or no new records."""
    result = PaginationResult()
    start_time = time.monotonic()

    while result.pages_scraped < config.max_pages:
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Placeholder: in real implementation, this would use Playwright
        # to check if the next button is present and clickable
        page_records: list[dict] = []
        # ---- end placeholder ----

        if config.stop_on_duplicates:
            page_records, _ = _remove_duplicates(page_records)

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


def _paginate_page_number(config: PaginationConfig) -> PaginationResult:
    """Iterate through numbered pages."""
    result = PaginationResult()
    start_time = time.monotonic()

    for _page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Placeholder: navigate to next page and extract
        page_records: list[dict] = []
        # ---- end placeholder ----

        if config.stop_on_duplicates:
            page_records, _ = _remove_duplicates(page_records)

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
    """Iterate through pages using URL parameter pattern."""
    result = PaginationResult()
    start_time = time.monotonic()

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Placeholder: construct URL and fetch
        if config.url_pattern:
            page_url = config.url_pattern.format(page=page_num)
            logger.debug("URL pattern page URL: %s", page_url)

        page_records: list[dict] = []
        # ---- end placeholder ----

        if config.stop_on_duplicates:
            page_records, _ = _remove_duplicates(page_records)

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
    """Scroll down bounded by max pages (scroll actions), records, and time."""
    result = PaginationResult()
    start_time = time.monotonic()

    for _scroll_num in range(config.max_pages):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Scroll and extract placeholder
        page_records: list[dict] = []
        # ---- end placeholder ----

        if config.stop_on_duplicates:
            page_records, _ = _remove_duplicates(page_records)

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


def _paginate_load_more(config: PaginationConfig) -> PaginationResult:
    """Click 'Load more' button until gone, max clicks, or no new records."""
    result = PaginationResult()
    start_time = time.monotonic()

    for _click_num in range(config.max_pages):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Placeholder: click load more and extract
        page_records: list[dict] = []
        # ---- end placeholder ----

        if config.stop_on_duplicates:
            page_records, _ = _remove_duplicates(page_records)

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def paginate(config: PaginationConfig | None = None) -> PaginationResult:
    """Execute pagination with the given configuration (synchronous, no browser).

    Args:
        config: Pagination configuration. Defaults to next-button strategy
            with 10 pages, 500 records max, 5 minute timeout.

    Returns:
        PaginationResult with extracted records and metadata. Since this is the
        sync version without a browser, records will always be empty. Use
        ``async_paginate()`` for live browser pagination.
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
    except Exception as exc:
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
