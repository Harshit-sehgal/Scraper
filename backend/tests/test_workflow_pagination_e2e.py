"""End-to-end test: workflow_executor aggregation through the scraper helpers.

Pins the contract added by closing the deferred CAND-P2-EXTRACTION-SCROLL-001
follow-up: workflows with ``pagination_config.strategy='load_more'`` MUST funnel
through the new ``scraper.run_load_more_extraction`` (and likewise for
``'infinite_scroll'``) so all extraction paths share a single
``ScrapeAttemptResult`` surface.

This test exercises the real Playwright-side surface area of the dispatcher
using a minimal mock page, then asserts the returned record set aggregates
across clicks instead of just one page.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_API_KEY", "wf-e2e")
os.environ.setdefault("DATAFORGE_OPERATOR_API_KEY", "wf-e2e")
os.environ.setdefault("DATAFORGE_ADMIN_API_KEY", "wf-e2e")
os.environ.setdefault("DATAFORGE_SESSION_SECRET", "wf-e2e")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")
os.environ.setdefault("PYTHONPATH", "backend")

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))


# ─── Mock Playwright page (matches test_scraper_scroll_load_more fixture) ─


class _MockLocator:
    def __init__(self, selector: str, page: _MockPage) -> None:
        self.selector = selector
        self.page = page

    @property
    def first(self) -> _MockLocator:
        return self

    async def is_visible(self, timeout: int = 0) -> bool:
        if not self.page.button_present:
            return False
        return any(token in self.selector for token in self.page.clickable_selectors)

    async def click(self) -> None:
        self.page.click_calls.append(self.selector)
        self.page.click_count += 1


class _MockPage:
    """Tiny Playwright page mock for the load_more click loop."""

    def __init__(self, *, button_present: bool = True) -> None:
        self.button_present = button_present
        self.clickable_selectors: list[str] = ["load-more", "load more"]
        self.click_calls: list[str] = []
        self.click_count: int = 0
        self.evaluate_calls: list[str] = []

    async def evaluate(self, script: str) -> Any:
        self.evaluate_calls.append(script)
        return None

    def locator(self, selector: str) -> _MockLocator:
        return _MockLocator(selector=selector, page=self)

    async def wait_for_function(self, script: str, timeout: int = 0) -> None:
        return None


# ─── Per-page extract shim ──────────────────────────────────────────────


@dataclass
class _ExtractStub:
    """Returns a pre-canned record chunk on each invocation."""

    call_count: int = 0
    records_per_call: list[list[dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, page: _MockPage) -> list[dict[str, Any]]:
        if self.call_count >= len(self.records_per_call):
            self.call_count += 1
            return []
        chunk = self.records_per_call[self.call_count]
        self.call_count += 1
        return chunk


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ─── Workflow fixture (in-memory only) ──────────────────────────────────


def _make_load_more_workflow(start_url: str) -> dict[str, Any]:
    """Build a workflow-dict with pagination_config.strategy='load_more'."""
    from app.models import WorkflowPaginationConfig, WorkflowStatus, WorkflowStep, WorkflowStepType

    pagination = WorkflowPaginationConfig(
        enabled=True,
        strategy="load_more",
        max_pages=4,
        selector=".load-more",
    )
    return {
        "id": "wf-e2e-load-more-001",
        "name": "Load More E2E",
        "description": "load_more aggregator e2e",
        "steps": [
            WorkflowStep(step_type=WorkflowStepType.OPEN, value=start_url),
        ],
        "extraction_schema": [],
        "pagination_config": pagination,
        "search_params": {},
        "status": WorkflowStatus.DRAFT,
        "mode": "workflow_replay",
        "start_url": start_url,
        "original_url": start_url,
        "auth_profile_id": None,
        "version": 1,
    }


# ─── Tests ──────────────────────────────────────────────────────────────


def test_workflow_load_more_dispatcher_routes_through_scraper() -> None:
    """A workflow with strategy='load_more' must aggregate records across clicks."""
    from app import workflow_executor
    from app.models import Workflow

    page = _MockPage(button_present=True)
    # Per-page extract returns 2 records on first click, 1 on second, 0 on third.
    extract_stub = _ExtractStub()
    extract_stub.records_per_call = [
        [{"title": "row-A"}, {"title": "row-B"}],
        [{"title": "row-C"}],
        [],
    ]

    workflow_dict = _make_load_more_workflow("https://example.com/feed?load_more=1")
    workflow = Workflow(**{k: v for k, v in workflow_dict.items() if k != "id"})
    # Override the auto-generated UUID so the assert can reference it deterministically.
    workflow.id = workflow_dict["id"]

    # The dispatcher's per-page extract needs to call the stub. Stub it via monkeypatch
    # of the underlying `_extract_records_from_page` function. (The dispatcher should
    # forward clicks via scraper.run_load_more_extraction and feed each successful click
    # through `_extract_records_from_page(page, workflow)`.)
    async def _per_page_stub(page_obj: Any, workflow: Workflow) -> list[dict[str, Any]]:
        return await extract_stub(page_obj)

    monkeypatched_extract = _per_page_stub
    workflow_executor._extract_records_from_page = monkeypatched_extract  # type: ignore[assignment]

    records, stopped_reason = _run(
        workflow_executor._paginate_and_extract(
            page=page,
            workflow=workflow,
        ),
    )

    # At least one load-more click must have been issued via scraper.run_load_more_extraction.
    assert any("load-more" in sel or "load more" in sel.lower() for sel in page.click_calls), (
        f"expected a load-more click; got click_calls={page.click_calls!r}"
    )
    # Records must aggregate across all clicks (NOT just the first page).
    titles = sorted(r["title"] for r in records)
    assert titles == ["row-A", "row-B", "row-C"], (
        f"expected aggregated record set, got {titles!r}; click_calls={page.click_calls!r}"
    )
    # Final stop reason must reflect the actual load-more loop exit condition.
    # Per ``app.pagination_executor._async_paginate_load_more``, the loop
    # exits with ``stopped_reason == 'no_new_records'`` when a click succeeded
    # but the per-page extract returned no new records (click_num > 0 case).
    # The mock page has 3 click iterations: 2 records, 1 record, 0 records.
    # With ``stop_on_duplicates=True`` and unique titles, the third click
    # triggers ``no_new_records`` cleanly — *not* button_gone, max_pages or
    # the empty-string fallback the previous turn's permissive set tolerated.
    assert stopped_reason == "no_new_records", (
        f"load_more loop with extracting-then-empty sequence must exit via 'no_new_records'; got {stopped_reason!r}"
    )


def test_workflow_load_more_no_button_returns_empty_quickly() -> None:
    """Workflow with strategy='load_more' against an absent button returns empty records."""
    from app import workflow_executor
    from app.models import Workflow

    page = _MockPage(button_present=False)
    extract_stub = _ExtractStub()

    workflow_dict = _make_load_more_workflow("https://example.com/feed")
    workflow = Workflow(**{k: v for k, v in workflow_dict.items() if k != "id"})
    workflow.id = workflow_dict["id"]

    async def _per_page_stub(page_obj: Any, workflow: Workflow) -> list[dict[str, Any]]:
        return await extract_stub(page_obj)

    workflow_executor._extract_records_from_page = _per_page_stub  # type: ignore[assignment]

    records, stopped_reason = _run(
        workflow_executor._paginate_and_extract(
            page=page,
            workflow=workflow,
        ),
    )

    # No clicks when no button was present.
    assert page.click_calls == [], f"unexpected click calls: {page.click_calls!r}"
    assert records == []

    # With button absent from iteration 1, ``_async_paginate_load_more``
    # exits via ``stopped_reason == 'button_gone'`` exactly — not an empty
    # string, not the catch-all that the previous permissive set tolerated.
    assert stopped_reason == "button_gone", (
        f"load_more loop with no visible button must exit via 'button_gone'; got {stopped_reason!r}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
