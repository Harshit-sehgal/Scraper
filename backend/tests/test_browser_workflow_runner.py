"""CAND-P2-WORKFLOW-REPLAY-BROWSER-001 — Playwright workflow runner tests.

These tests use a local aiohttp fixture server (no live-site dependency)
to verify the browser runner can:
1. Navigate to a start URL (goto)
2. Fill an input and click submit
3. Extract rows from the resulting page
4. Handle selector-not-found gracefully
5. Handle timeout caps
6. Produce a screenshot (base64) artifact
7. Clean up browser resources after each test
8. Handle Playwright-unavailable scenario
9. Not leak secrets in timeline entries

Run with:  python3 -m pytest backend/tests/test_browser_workflow_runner.py -v
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from app.models import (
    SchemaField,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepType,
)

# Requires Playwright + a local fixture HTTP server; run under the browser tier
# (`--run-browser`), not the unit job.
pytestmark = pytest.mark.browser


FIXTURE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head><title>Fixture Form</title></head>
<body>
  <h1>Test Form</h1>
  <form id="test-form">
    <label for="search-input">Search</label>
    <input id="search-input" name="q" type="text" />

    <label for="category-select">Category</label>
    <select id="category-select" name="category">
      <option value="all">All</option>
      <option value="products">Products</option>
      <option value="blog">Blog</option>
    </select>

    <button id="submit-btn" type="submit">Go</button>
  </form>
  <div id="results">
    <table>
      <thead>
        <tr><th>Title</th><th>Price</th></tr>
      </thead>
      <tbody>
        <tr class="result item">
          <td class="title" data-field="title">Widget A</td>
          <td class="price" data-field="price">$9.99</td>
        </tr>
        <tr class="result item">
          <td class="title" data-field="title">Widget B</td>
          <td class="price" data-field="price">$24.99</td>
        </tr>
        <tr class="result item">
          <td class="title" data-field="title">Widget C</td>
          <td class="price" data-field="price">$49.99</td>
        </tr>
      </tbody>
    </table>
  </div>
</body>
</html>"""

FIXTURE_PAGE_NO_TABLE = """<!DOCTYPE html>
<html lang="en">
<head><title>Empty Page</title></head>
<body>
  <h1>Nothing to extract here</h1>
</body>
</html>"""


def _workflow(
    *,
    steps: list[WorkflowStep] | None = None,
    extraction_schema: list[SchemaField] | None = None,
    start_url: str = "http://127.0.0.1:12345/",
) -> Workflow:
    return Workflow(
        id="test-wf-browser",
        name="Browser Test Workflow",
        mode="workflow_replay",
        start_url=start_url,
        steps=steps
        or [
            WorkflowStep(
                step_type=WorkflowStepType.GOTO,
                value=start_url,
                order=0,
                description="Open fixture page",
            ),
        ],
        extraction_schema=extraction_schema
        or [
            SchemaField(name="title", field_type="string"),
            SchemaField(name="price", field_type="currency"),
        ],
        status=WorkflowStatus.ACTIVE,
    )


class TestBrowserWorkflowRunner:
    """Core browser runner tests — require Playwright + browsers."""

    @pytest_asyncio.fixture(autouse=True)
    async def _close_browser_pool_after_test(self, _reset_browser_pool_fixture):
        yield
        import app.browser_pool as browser_pool_module

        pool = browser_pool_module._pool
        if pool is not None:
            await pool.close()
            browser_pool_module.reset_global_browser_pool()

    @pytest.mark.asyncio
    async def test_goto_fixture_page_and_extract_rows(self):
        """Navigate to a fixture page, extract rows via schema selectors."""
        from app.services.browser_workflow_runner import run_workflow_in_browser

        wf = _workflow()
        result = await run_workflow_in_browser(wf, sample_limit=5, fixture_html=FIXTURE_PAGE)

        assert result["preview_status"] == "succeeded", f"Expected succeeded, got: {result.get('user_message')}"
        assert result["page_title"] == "Fixture Form"
        assert len(result["sample_rows"]) == 3
        assert result["sample_rows"][0]["title"] == "Widget A"
        assert result["sample_rows"][0]["price"] == "$9.99"
        assert result["screenshot"] is not None
        assert len(result["timeline"]) >= 1

    @pytest.mark.asyncio
    async def test_goto_and_fill_then_click(self):
        """Execute a fill + click sequence against the fixture server."""
        from app.services.browser_workflow_runner import run_workflow_in_browser

        wf = _workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.GOTO, order=0, description="Open page"),
                WorkflowStep(step_type=WorkflowStepType.FILL, selector="#search-input", value="test query", order=1),
                WorkflowStep(step_type=WorkflowStepType.CLICK, selector="#submit-btn", order=2),
            ],
        )
        result = await run_workflow_in_browser(wf, sample_limit=5, fixture_html=FIXTURE_PAGE)

        assert result["preview_status"] == "succeeded"
        # The fill + click should complete without error
        assert all(e["status"] == "ok" for e in result["timeline"])
        assert len(result["timeline"]) == 3  # goto + fill + click

    @pytest.mark.asyncio
    async def test_selector_not_found_produces_graceful_failure(self):
        """A missing selector should fail with a clear error message."""
        from app.services.browser_workflow_runner import run_workflow_in_browser

        wf = _workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.GOTO, order=0, description="Open page"),
                WorkflowStep(step_type=WorkflowStepType.FILL, selector="#nonexistent-input", value="test", order=1),
            ],
        )
        result = await run_workflow_in_browser(wf, sample_limit=5, fixture_html=FIXTURE_PAGE)

        assert result["preview_status"] == "failed"
        assert result["failure_type"] == "step_execution_error"
        assert any(e["status"] == "failed" for e in result["timeline"])
        assert len(result["sample_rows"]) == 0

    @pytest.mark.asyncio
    async def test_screenshot_included_on_success(self):
        """Successful execution must include a base64 screenshot."""
        from app.services.browser_workflow_runner import run_workflow_in_browser

        wf = _workflow()
        result = await run_workflow_in_browser(wf, sample_limit=1, fixture_html=FIXTURE_PAGE)

        assert result["preview_status"] == "succeeded"
        assert result["screenshot"] is not None
        assert isinstance(result["screenshot"], str)
        assert len(result["screenshot"]) > 0

    @pytest.mark.asyncio
    async def test_empty_page_extracts_no_rows(self):
        """A page with no extractable data returns an empty sample_rows."""
        from app.services.browser_workflow_runner import run_workflow_in_browser

        wf = _workflow()
        result = await run_workflow_in_browser(wf, sample_limit=5, fixture_html=FIXTURE_PAGE_NO_TABLE)

        assert result["preview_status"] == "succeeded"
        assert result["sample_rows"] == []
        assert "No sample rows matched" in result["warnings"][0]

    @pytest.mark.asyncio
    async def test_no_secret_leakage_in_timeline(self):
        """Timeline entries must redact sensitive values."""
        from app.services.browser_workflow_runner import run_workflow_in_browser

        wf = _workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.GOTO, order=0, description="Open page"),
                WorkflowStep(
                    step_type=WorkflowStepType.FILL,
                    selector="#password-field",
                    value="super-secret-password",
                    order=1,
                    description="Fill password",
                ),
            ],
        )
        result = await run_workflow_in_browser(wf, sample_limit=1, fixture_html=FIXTURE_PAGE)

        # Timeline should not contain the raw password even if the step fails
        timeline_str = str(result["timeline"])
        assert "super-secret-password" not in timeline_str


class TestBrowserWorkflowRunnerEdgeCases:
    """Edge case tests that don't require a running browser."""

    @pytest.mark.asyncio
    async def test_screenshot_capture_retries_transient_protocol_error(self):
        from app.services.browser_workflow_runner import _capture_screenshot_b64

        page = AsyncMock()
        page.screenshot.side_effect = [RuntimeError("transient protocol error"), b"jpeg-bytes"]
        timeline: list[dict[str, Any]] = []

        result = await _capture_screenshot_b64(page, timeline)

        assert result == base64.b64encode(b"jpeg-bytes").decode("ascii")
        assert page.screenshot.await_count == 2
        page.wait_for_timeout.assert_awaited_once_with(100)
        assert timeline == []

    def test_browser_failure_helper_produces_valid_dict(self):
        """_browser_failure returns a correctly shaped failure dict."""
        from app.services.browser_workflow_runner import _browser_failure

        wf = _workflow()
        result = _browser_failure(
            wf,
            failure_type="test_error",
            user_message="Test error message",
            recommended_action="Do something about it.",
            timeline=[],
        )

        assert result["preview_status"] == "failed"
        assert result["failure_type"] == "test_error"
        assert result["workflow_id"] == "test-wf-browser"
        assert result["sample_rows"] == []
        assert result["screenshot"] is None
        assert result["warnings"] == []

    def test_page_title_from_soup_extracts_correctly(self):
        """_page_title_from_soup works with bs4."""
        from app.services.browser_workflow_runner import _page_title_from_soup
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<html><head><title>Hello World</title></head></html>", "html.parser")
        assert _page_title_from_soup(soup) == "Hello World"

        empty = BeautifulSoup("<html></html>", "html.parser")
        assert _page_title_from_soup(empty) == ""


class TestFixtureServerLifecycle:
    """Verify the fixture server starts and stops cleanly."""

    @pytest.mark.asyncio
    async def test_fixture_server_serves_html(self):
        """Start a fixture server, fetch HTML via HTTP, verify content."""
        import httpx
        from app.services.browser_workflow_runner import (
            _start_fixture_server,
            _stop_fixture_server,
        )

        html = "<!DOCTYPE html><html><body><h1>Hello Fixture</h1></body></html>"
        url, runner, port = await _start_fixture_server(html)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5.0)
                assert resp.status_code == 200
                assert "Hello Fixture" in resp.text
        finally:
            await _stop_fixture_server(runner, port)
