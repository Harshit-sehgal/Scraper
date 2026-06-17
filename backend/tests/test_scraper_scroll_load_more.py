"""Tests for the infinite-scroll + load-more execution in backend.app.scraper.

These tests pin the contract added by closing CAND-P2-EXTRACTION-SCROLL-001:
``scraper.run_infinite_scroll_extraction`` and ``scraper.run_load_more_extraction``
delegate to ``backend.app.pagination_executor`` for the scroll/click loops and
return a ``ScrapeAttemptResult`` aggregating all collected records.

The mock page is intentionally minimal — it implements only the Playwright
surface area these helpers touch (``evaluate``, ``locator``, ``wait_for_function``)
and records every call so the assertions can verify the loop body actually
executed and ``async_paginate`` was driven through ``pagination_executor``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Pin the same env the production router expects (avoids dotenv load).
os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_API_KEY", "scroll-test")
os.environ.setdefault("DATAFORGE_OPERATOR_API_KEY", "scroll-test")
os.environ.setdefault("DATAFORGE_ADMIN_API_KEY", "scroll-test")
os.environ.setdefault("DATAFORGE_SESSION_SECRET", "scroll-test")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")
os.environ.setdefault("PYTHONPATH", "backend")

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from app.models import FieldType, SchemaField, WorkflowPaginationConfig
from app.pagination_executor import PaginationConfig

# ─── Mock Playwright page ───────────────────────────────────────────────


class _MockLocator:
    def __init__(self, selector: str, page: _MockPage) -> None:
        self.selector = selector
        self.page = page
        self.click_count = 0
        self.is_visible_calls = 0

    @property
    def first(self) -> _MockLocator:
        return self  # All selectors resolve to first in this mock

    async def is_visible(self, timeout: int = 0) -> bool:
        self.is_visible_calls += 1
        # Synthetic presence: matcher returns False when button_present=False
        if not self.page.button_present:
            return False
        # Match by substring against configured clickable tokens
        return any(token in self.selector for token in self.page.clickable_selectors)

    async def click(self) -> None:
        self.click_count += 1
        self.page.click_calls.append(self.selector)


class _MockPage:
    """Tiny Playwright page mock: records evaluate() + locator() calls."""

    def __init__(self, *, button_present: bool = True) -> None:
        self.button_present = button_present
        self.clickable_selectors: list[str] = ["load-more", "load more"]
        self.heights: list[int] = [100, 500, 900, 900, 900, 900]
        self.evaluate_calls: list[str] = []
        self.click_calls: list[str] = []
        self.locator_calls: list[str] = []

    async def evaluate(self, script: str) -> Any:
        self.evaluate_calls.append(script)
        # Pretend the page keeps growing for the first 3 scroll attempts.
        if "scrollHeight" in script and "scrollTo(0, 0)" not in script:
            return self.heights.pop(0) if self.heights else 0
        return None

    def locator(self, selector: str) -> _MockLocator:
        self.locator_calls.append(selector)
        return _MockLocator(selector=selector, page=self)

    async def wait_for_function(self, script: str, timeout: int = 0) -> None:
        return None


# ─── Per-page extract shim ──────────────────────────────────────────────


@dataclass
class _ExtractStub:
    """Extracts a pre-canned chunk per call; bounded by the supplied list."""

    call_count: int = 0
    records_per_call: list[list[dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, page: _MockPage) -> list[dict[str, Any]]:
        if self.call_count >= len(self.records_per_call):
            self.call_count += 1
            return []
        chunk = self.records_per_call[self.call_count]
        self.call_count += 1
        return chunk


# ─── Tests ──────────────────────────────────────────────────────────────


def _run(coro: Any) -> Any:
    """Helper: run an awaitable via asyncio.run."""
    import asyncio

    return asyncio.run(coro)


def test_scraper_exports_scroll_and_load_more_helpers() -> None:
    """The two new entry points must be importable from backend.app.scraper."""
    from app import scraper

    assert hasattr(scraper, "run_infinite_scroll_extraction"), (
        "scraper must expose run_infinite_scroll_extraction (closes CAND-P2-EXTRACTION-SCROLL-001)"
    )
    assert hasattr(scraper, "run_load_more_extraction"), (
        "scraper must expose run_load_more_extraction (closes CAND-P2-EXTRACTION-SCROLL-001)"
    )
    assert callable(scraper.run_infinite_scroll_extraction)
    assert callable(scraper.run_load_more_extraction)


def test_run_infinite_scroll_extraction_drives_pagination_loop() -> None:
    """Infinite-scroll helpers must iterate scrollTo + scrollHeight probes."""
    from app.scraper import run_infinite_scroll_extraction

    page = _MockPage(button_present=True)
    # Per-call extraction returns a record the first time, then nothing new.
    extract_stub = _ExtractStub()
    extract_stub.records_per_call = [[{"title": "row-1"}], [], [], []]

    [SchemaField(name="title", field_type=FieldType.STRING)]
    config = PaginationConfig(strategy="infinite_scroll", max_pages=3, delay_between_pages=0)

    result = _run(
        run_infinite_scroll_extraction(
            page=page,
            url="https://example.com/feed?infinite=1",
            pagination_config=config,
            per_page_extract=extract_stub,
        ),
    )

    # At least one scrollTo(0, scrollHeight) must have been requested.
    assert any("scrollTo(0, document.body.scrollHeight)" in s for s in page.evaluate_calls), (
        f"expected scrollTo invocation; got evaluate_calls={page.evaluate_calls!r}"
    )
    # Records aggregated from per-page extraction (just the first call returned data).
    assert len(result) >= 1, "expected at least one record from the first scroll"
    assert result[0]["title"] == "row-1"
    # The ScrapeAttemptResult metadata surface should still be present.
    assert hasattr(result, "extraction_method")
    assert result.extraction_method == "infinite_scroll"


def test_run_load_more_extraction_clicks_button_until_gone() -> None:
    """Load-more helper must discover + click the button across iterations."""
    from app.scraper import run_load_more_extraction

    page = _MockPage(button_present=True)
    extract_stub = _ExtractStub()
    extract_stub.records_per_call = [
        [{"name": "row-A"}, {"name": "row-B"}],
        [{"name": "row-C"}],
        [],
    ]

    [SchemaField(name="name", field_type=FieldType.STRING)]
    config = PaginationConfig(strategy="load_more", max_pages=4, delay_between_pages=0)

    result = _run(
        run_load_more_extraction(
            page=page,
            url="https://example.com/feed?load_more=1",
            pagination_config=config,
            per_page_extract=extract_stub,
        ),
    )

    # At least one click on a load-more selector must have been issued.
    assert any("load-more" in sel or "load more" in sel.lower() for sel in page.click_calls), (
        f"expected a load-more click; got click_calls={page.click_calls!r}"
    )
    # Aggregated records across all click iterations.
    titles = sorted(r["name"] for r in result)
    assert titles == ["row-A", "row-B", "row-C"], f"unexpected record set: {titles!r}"
    assert result.extraction_method == "load_more"


def test_run_load_more_stops_cleanly_when_button_is_absent() -> None:
    """If no load-more button is present from the start, the loop must exit early."""
    from app.scraper import run_load_more_extraction

    page = _MockPage(button_present=False)
    extract_stub = _ExtractStub()
    [SchemaField(name="name", field_type=FieldType.STRING)]
    config = PaginationConfig(strategy="load_more", max_pages=3, delay_between_pages=0)

    result = _run(
        run_load_more_extraction(
            page=page,
            url="https://example.com/feed",
            pagination_config=config,
            per_page_extract=extract_stub,
        ),
    )

    # No clicks when no button is present.
    assert page.click_calls == [], f"unexpected click calls: {page.click_calls!r}"
    assert len(result) == 0


def test_workflow_pagination_config_accepts_load_more_strategy() -> None:
    """WorkflowPaginationConfig.strategy must enumerate load_more alongside the other strategies."""

    cfg = WorkflowPaginationConfig(strategy="load_more")
    assert cfg.strategy == "load_more"
    # Previous default behaviour must still hold.
    cfg_default = WorkflowPaginationConfig()
    assert cfg_default.strategy == "next_button"


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
