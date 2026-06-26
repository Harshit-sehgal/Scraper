"""Unit tests for app.workflow_executor — replay / extract / paginate logic.

These tests mock the Playwright page object and browser pool so no real
browser is needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import (
    FieldType,
    SchemaField,
    Workflow,
    WorkflowPaginationConfig,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepType,
)
from app.workflow_executor import (
    _extract_records_from_page,
    _paginate_and_extract,
    _replay_steps,
    execute_workflow,
    preview_workflow,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _make_workflow(**overrides) -> Workflow:
    defaults = {
        "id": "wf_test",
        "name": "Test Workflow",
        "original_url": "https://example.com",
        "start_url": "https://example.com",
        "steps": [],
        "extraction_schema": [],
        "status": WorkflowStatus.ACTIVE,
        "created_at": "2026-01-01T00:00:00Z",
        "user_id": "user_1",
    }
    defaults.update(overrides)
    return Workflow(**defaults)


def _mock_page() -> AsyncMock:
    page = AsyncMock()
    page.url = "https://example.com/result"
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock()
    page.press = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.title = AsyncMock(return_value="Test Page")
    page.wait_for_load_state = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.close = AsyncMock()

    locator = AsyncMock()
    locator.is_visible = AsyncMock(return_value=True)
    locator.is_checked = AsyncMock(return_value=False)
    locator.check = AsyncMock()
    locator.uncheck = AsyncMock()
    page.locator = MagicMock(return_value=locator)

    return page


# ── _replay_steps ────────────────────────────────────────────────────────


class TestReplaySteps:
    @pytest.mark.asyncio
    async def test_goto_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.GOTO, value="https://example.com"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert len(timeline) == 1
        assert timeline[0]["action"] == "goto"
        assert timeline[0]["status"] == "ok"
        page.goto.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_step_alias(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.OPEN, value="https://example.com"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_click_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.CLICK, selector="#btn"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["action"] == "click"
        page.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fill_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.FILL, selector="input", value="hello"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["status"] == "ok"
        page.fill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_select_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.SELECT, selector="select#opt", value="val"),
            ]
        )
        await _replay_steps(page, wf)
        page.select_option.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_step(self):
        page = _mock_page()
        locator = page.locator.return_value
        locator.is_checked = AsyncMock(return_value=False)
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.CHECK, selector="#chk"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        locator.check.assert_awaited_once()
        assert timeline[0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_uncheck_step(self):
        page = _mock_page()
        locator = page.locator.return_value
        locator.is_checked = AsyncMock(return_value=True)
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.UNCHECK, selector="#chk"),
            ]
        )
        await _replay_steps(page, wf)
        locator.uncheck.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_press_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.PRESS, selector="input", value="Enter"),
            ]
        )
        await _replay_steps(page, wf)
        page.press.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scroll_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.SCROLL),
            ]
        )
        await _replay_steps(page, wf)
        page.evaluate.assert_awaited()

    @pytest.mark.asyncio
    async def test_wait_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.WAIT, value="100"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_wait_for_url_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.WAIT_FOR_URL, value="https://example.com/done"),
            ]
        )
        await _replay_steps(page, wf)
        page.wait_for_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wait_for_selector_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.WAIT_FOR_SELECTOR, selector="#result"),
            ]
        )
        await _replay_steps(page, wf)
        page.wait_for_selector.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wait_for_text_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.WAIT_FOR_TEXT, value="Done"),
            ]
        )
        await _replay_steps(page, wf)
        page.wait_for_selector.assert_awaited()

    @pytest.mark.asyncio
    async def test_wait_for_timeout_limited_step(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.WAIT_FOR_TIMEOUT_LIMITED, value="200"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_extract_step_deferred(self):
        page = _mock_page()
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.EXTRACT),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["status"] == "deferred"

    @pytest.mark.asyncio
    async def test_failed_step_continues(self):
        page = _mock_page()
        page.click = AsyncMock(side_effect=RuntimeError("Element not found"))
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.CLICK, selector="#missing"),
                WorkflowStep(step_type=WorkflowStepType.SCROLL),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert len(timeline) == 2
        assert timeline[0]["status"] == "failed"
        assert "error" in timeline[0]
        assert timeline[1]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_networkidle_timeout_during_goto(self):
        page = _mock_page()
        page.wait_for_load_state = AsyncMock(side_effect=RuntimeError("timeout"))
        wf = _make_workflow(
            steps=[
                WorkflowStep(step_type=WorkflowStepType.GOTO, value="https://example.com"),
            ]
        )
        timeline = await _replay_steps(page, wf)
        assert timeline[0]["status"] == "ok"


# ── _extract_records_from_page ───────────────────────────────────────────


class TestExtractRecordsFromPage:
    @pytest.mark.asyncio
    async def test_no_schema_returns_empty(self):
        page = _mock_page()
        wf = _make_workflow(extraction_schema=[])
        result = await _extract_records_from_page(page, wf)
        assert result == []

    @pytest.mark.asyncio
    async def test_with_schema(self):
        page = _mock_page()
        page.evaluate = AsyncMock(return_value=[{"title": "Hello"}])
        wf = _make_workflow(
            extraction_schema=[
                SchemaField(name="title", field_type=FieldType.STRING),
            ]
        )
        result = await _extract_records_from_page(page, wf)
        assert result == [{"title": "Hello"}]

    @pytest.mark.asyncio
    async def test_extraction_failure_returns_empty(self):
        page = _mock_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError("JS error"))
        wf = _make_workflow(
            extraction_schema=[
                SchemaField(name="title", field_type=FieldType.STRING),
            ]
        )
        result = await _extract_records_from_page(page, wf)
        assert result == []


# ── _paginate_and_extract ────────────────────────────────────────────────


class TestPaginateAndExtract:
    @pytest.mark.asyncio
    async def test_no_pagination_config(self):
        page = _mock_page()
        page.evaluate = AsyncMock(return_value=[{"x": "1"}])
        wf = _make_workflow(
            extraction_schema=[SchemaField(name="x", field_type=FieldType.STRING)],
        )
        records, reason = await _paginate_and_extract(page, wf)
        assert reason == "no_pagination"

    @pytest.mark.asyncio
    async def test_disabled_pagination(self):
        page = _mock_page()
        wf = _make_workflow(
            pagination_config=WorkflowPaginationConfig(enabled=False),
        )
        records, reason = await _paginate_and_extract(page, wf)
        assert reason == "no_pagination"


# ── execute_workflow ─────────────────────────────────────────────────────


class TestExecuteWorkflow:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        page = _mock_page()
        page.evaluate = AsyncMock(return_value=[{"title": "Result"}])

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow(
            extraction_schema=[SchemaField(name="title", field_type=FieldType.STRING)],
        )

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await execute_workflow(wf)

        assert result["status"] in ("succeeded", "completed_empty")
        assert result["workflow_id"] == "wf_test"
        assert "duration_seconds" in result
        page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_navigation_failure(self):
        page = _mock_page()
        page.goto = AsyncMock(side_effect=RuntimeError("Connection refused"))

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await execute_workflow(wf)

        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_exception_during_execution(self):
        mock_pool = MagicMock()
        mock_pool.get_context = AsyncMock(side_effect=RuntimeError("Pool error"))

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await execute_workflow(wf)

        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_page_close_failure_suppressed(self):
        page = _mock_page()
        page.close = AsyncMock(side_effect=RuntimeError("Close failed"))

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await execute_workflow(wf)
        assert result["workflow_id"] == "wf_test"

    @pytest.mark.asyncio
    async def test_networkidle_timeout_during_initial_nav(self):
        page = _mock_page()
        page.wait_for_load_state = AsyncMock(side_effect=TimeoutError("idle timeout"))

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await execute_workflow(wf)
        assert result["workflow_id"] == "wf_test"

    @pytest.mark.asyncio
    async def test_title_failure_fallback(self):
        page = _mock_page()
        page.title = AsyncMock(side_effect=RuntimeError("Page closed"))

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await execute_workflow(wf)
        assert result["page_title"] == ""
        assert result["final_url"] == "https://example.com"


# ── preview_workflow ─────────────────────────────────────────────────────


class TestPreviewWorkflow:
    @pytest.mark.asyncio
    async def test_successful_preview(self):
        page = _mock_page()
        page.evaluate = AsyncMock(return_value=[{"title": f"Row {i}"} for i in range(10)])

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow(
            extraction_schema=[SchemaField(name="title", field_type=FieldType.STRING)],
        )

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await preview_workflow(wf)

        assert result["preview_status"] == "succeeded"
        assert result["record_count"] <= 5  # capped at 5

    @pytest.mark.asyncio
    async def test_preview_with_no_results(self):
        page = _mock_page()
        page.evaluate = AsyncMock(return_value=[])

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow(
            extraction_schema=[SchemaField(name="title", field_type=FieldType.STRING)],
        )

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await preview_workflow(wf)

        assert result["preview_status"] == "succeeded"
        assert "warnings" in result
        assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_preview_failure(self):
        mock_pool = MagicMock()
        mock_pool.get_context = AsyncMock(side_effect=RuntimeError("Pool error"))

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await preview_workflow(wf)

        assert result["preview_status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_preview_page_close_failure_suppressed(self):
        page = _mock_page()
        page.close = AsyncMock(side_effect=RuntimeError("Close failed"))

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=page)
        mock_pool.get_context = AsyncMock(return_value=mock_context)

        wf = _make_workflow()

        with patch("app.browser_pool.get_browser_pool", return_value=mock_pool):
            result = await preview_workflow(wf)
        assert result["workflow_id"] == "wf_test"
