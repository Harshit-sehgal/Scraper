"""Pagination Executor — bounded extraction for multi-page sites.

Supports next-button, page-number, URL-parameter, infinite-scroll,
and load-more patterns. All modes enforce hard limits on pages,
records, and runtime.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_RECORDS = 500
DEFAULT_MAX_RUNTIME_SECONDS = 300
DEFAULT_DELAY_BETWEEN_PAGES = 1.0


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

    strategy: str = "next_button"  # next_button, page_number, url_parameter, infinite_scroll, load_more
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
# Pagination strategies (placeholders for live browser)
# ---------------------------------------------------------------------------


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

    for page_num in range(1, config.max_pages + 1):
        if time.monotonic() - start_time > config.max_runtime_seconds:
            result.stopped_reason = "timeout"
            break

        # Placeholder: navigate to page_num and extract
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


def _paginate_url_parameter(config: PaginationConfig) -> PaginationResult:
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

    for scroll_num in range(config.max_pages):
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

    for click_num in range(config.max_pages):
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
    """Execute pagination with the given configuration.

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
        "url_parameter": _paginate_url_parameter,
        "infinite_scroll": _paginate_infinite_scroll,
        "load_more": _paginate_load_more,
    }

    strategy_fn = strategy_map.get(config.strategy, _paginate_next_button)

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
    strategy: str = "next_button",
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
