"""Workflow Executor — replay saved scraping workflows with Playwright.

Experimental — not wired into the production job lifecycle.
============================================================

This module provides the execution engine for saved workflows. Each
workflow is a sequence of steps (open, fill, click, etc.) that are
replayed against a live Playwright browser. After the steps complete,
the configured extraction schema is applied to the final page state.

Pagination strategies (infinite scroll, load more, next button) are
handled via ``app.pagination_executor.async_paginate``.

**Status**: Tested but not yet integrated into the production scraper
pipeline.  To activate, import and call from the job runner.  Until
then, this module lives alongside the research shell but is not
registered in ``RESEARCH_MODULES`` because it has a clear near-term
promotion path (unlike the open-ended research experiments).
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from typing import Any

from app.models import Workflow, WorkflowStepType

logger = logging.getLogger(__name__)

# Cap on how long a single step can wait
MAX_STEP_TIMEOUT_MS = 15_000
# Extra time after clicking/loading for JS rendering
PAGE_SETTLE_SECONDS = 1.5


async def _replay_steps(page: Any, workflow: Workflow) -> list[dict[str, Any]]:
    """Replay workflow steps against a live Playwright page.

    Returns a timeline of step events with status (ok, failed, skipped).
    """
    timeline: list[dict[str, Any]] = []

    for step in sorted(workflow.steps, key=lambda x: x.order):
        event: dict[str, Any] = {
            "order": step.order,
            "action": step.step_type.value,
            "selector": step.selector,
            "value": step.value,
            "status": "ok",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        try:
            if step.step_type in (WorkflowStepType.GOTO, WorkflowStepType.OPEN):
                await page.goto(step.value or workflow.start_url, wait_until="domcontentloaded", timeout=MAX_STEP_TIMEOUT_MS)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except (RuntimeError, OSError, ValueError):
                    logger.debug("networkidle timeout during goto step %d, continuing", step.order)
                await asyncio.sleep(PAGE_SETTLE_SECONDS)
                event["url"] = page.url

            elif step.step_type == WorkflowStepType.CLICK:
                await page.click(step.selector, timeout=MAX_STEP_TIMEOUT_MS)
                await asyncio.sleep(PAGE_SETTLE_SECONDS)

            elif step.step_type == WorkflowStepType.FILL:
                await page.fill(step.selector, step.value, timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.SELECT:
                await page.select_option(step.selector, step.value, timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.CHECK:
                locator = page.locator(step.selector)
                if await locator.is_visible() and not await locator.is_checked():
                    await locator.check(timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.UNCHECK:
                locator = page.locator(step.selector)
                if await locator.is_visible() and await locator.is_checked():
                    await locator.uncheck(timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.PRESS:
                await page.press(step.selector, step.value or "Enter", timeout=MAX_STEP_TIMEOUT_MS)
                await asyncio.sleep(PAGE_SETTLE_SECONDS)

            elif step.step_type == WorkflowStepType.SCROLL:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(PAGE_SETTLE_SECONDS)

            elif step.step_type == WorkflowStepType.WAIT:
                wait_ms = int(step.value or "1000")
                await asyncio.sleep(min(wait_ms, MAX_STEP_TIMEOUT_MS) / 1000.0)

            elif step.step_type == WorkflowStepType.WAIT_FOR_URL:
                await page.wait_for_url(step.value, timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.WAIT_FOR_SELECTOR:
                await page.wait_for_selector(step.selector, timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.WAIT_FOR_TEXT:
                await page.wait_for_selector(f"text={step.value}", timeout=MAX_STEP_TIMEOUT_MS)

            elif step.step_type == WorkflowStepType.WAIT_FOR_TIMEOUT_LIMITED:
                max_wait = min(int(step.value or "1000"), MAX_STEP_TIMEOUT_MS)
                await asyncio.sleep(max_wait / 1000.0)

            elif step.step_type == WorkflowStepType.EXTRACT:
                # EXTRACT is handled separately by the extraction schema
                event["status"] = "deferred"

        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            logger.warning("Workflow step %d (%s) failed: %s", step.order, step.step_type.value, exc)
            event["status"] = "failed"
            event["error"] = str(exc)
            # Continue with remaining steps

        timeline.append(event)

    return timeline


async def _extract_records_from_page(
    page: Any,
    workflow: Workflow,
) -> list[dict[str, Any]]:
    """Extract records from the current page using the workflow's extraction schema.

    Uses Playwright's ``page.evaluate()`` to run the selectors defined
    in ``workflow.extraction_schema`` against the page DOM.
    """
    if not workflow.extraction_schema:
        return []

    records: list[dict[str, Any]] = []
    try:
        # Try to find repeating containers first
        records = await page.evaluate(
            """(schema) => {
                const results = [];
                // Try common container selectors
                const containers = document.querySelectorAll(
                    'table tbody tr, .result, .item, article, [class*="card"], [class*="item"], li'
                );
                for (const container of containers) {
                    const row = {};
                    let hasData = false;
                    for (const field of schema) {
                        const name = field.name;
                        const selectors = [
                            `[data-field="${name}"]`,
                            `[itemprop="${name}"]`,
                            `[name="${name}"]`,
                            `.${name}`,
                            `[class*="${name}"]`,
                        ];
                        let value = '';
                        for (const sel of selectors) {
                            const el = container.querySelector(sel);
                            if (el) {
                                value = (el.textContent || el.value || '').trim();
                                if (value) break;
                            }
                        }
                        // Fallback: try matching by field type
                        if (!value && field.field_type === 'email') {
                            const emailEl = container.querySelector('a[href^="mailto:"]');
                            if (emailEl) {
                                const href = emailEl.getAttribute('href') || '';
                                value = href.replace('mailto:', '').split('?')[0];
                            }
                        }
                        if (!value && field.field_type === 'phone') {
                            const telEl = container.querySelector('a[href^="tel:"]');
                            if (telEl) {
                                const href = telEl.getAttribute('href') || '';
                                value = href.replace('tel:', '').split('?')[0];
                            }
                        }
                        if (!value && field.field_type === 'url') {
                            const link = container.querySelector('a[href]');
                            if (link) value = link.getAttribute('href') || '';
                        }
                        row[name] = value;
                        if (value) hasData = true;
                    }
                    if (hasData) results.push(row);
                }
                return results;
            }""",
            [{"name": f.name, "field_type": f.field_type.value} for f in workflow.extraction_schema],
        )
    except (RuntimeError, OSError, ValueError) as exc:
        logger.warning("Page extraction failed: %s", exc)

    return records


async def _paginate_and_extract(
    page: Any,
    workflow: Workflow,
) -> tuple[list[dict[str, Any]], str]:
    """Handle pagination if configured and extract all records.

    Returns (all_records, pagination_stopped_reason).

    When ``pagination_config.strategy`` is ``load_more`` or ``infinite_scroll``,
    dispatches through the new ``app.scraper`` helpers so all extraction paths
    funnel through a single ``ScrapeAttemptResult`` surface. Other strategies
    fall through to ``app.pagination_executor.async_paginate`` directly.
    """
    pagination_config = workflow.pagination_config
    if not pagination_config or not pagination_config.enabled:
        # No pagination, just extract from current page
        records = await _extract_records_from_page(page, workflow)
        return records, "no_pagination"

    async def _extract(page_arg: Any) -> list[dict[str, Any]]:
        return await _extract_records_from_page(page_arg, workflow)

    strategy = pagination_config.strategy

    # Funnel scroll-style strategies through the new scraper helpers so the
    # workflow extraction path shares its ScrapeAttemptResult surface with
    # the public scrape_url() / run_infinite_scroll_extraction() / etc. APIs.
    #
    # ``workflow.pagination_config`` is the API-side model which intentionally
    # omits executor-only fields like ``max_records``, so we materialise a
    # full ``PaginationConfig`` here (mirroring the next_button / page_number
    # fall-through) before passing it through the helper chain.
    if strategy in ("load_more", "infinite_scroll"):
        from app import scraper
        from app.pagination_executor import PaginationConfig as ExecutorPaginationConfig
        from app.scraper_models import ScrapeAttemptResult

        executor_config = ExecutorPaginationConfig(
            strategy=strategy,
            max_pages=pagination_config.max_pages,
            selector=pagination_config.selector or None,
            stop_on_duplicates=True,
        )

        helper = scraper.run_load_more_extraction if strategy == "load_more" else scraper.run_infinite_scroll_extraction
        # Run the helper under an isolated local so Mypy doesn't reuse this
        # binding for the next ``sync_paginate`` branch below. ``ScrapeAttemptResult``
        # subclasses ``list`` so it already satisfies the ``list[dict[str, Any]]`` slot.
        scroll_result: ScrapeAttemptResult = await helper(
            page,
            workflow.start_url,
            pagination_config=executor_config,
            per_page_extract=_extract,
        )
        # ``stopped_reason`` is now a first-class attribute on ``ScrapeAttemptResult``
        # (populated by ``_run_paginated_extraction`` from ``pagination_result.stopped_reason``).
        return scroll_result, scroll_result.stopped_reason

    from app.pagination_executor import PaginationConfig, async_paginate

    config = PaginationConfig(
        strategy=strategy,
        max_pages=pagination_config.max_pages,
        selector=pagination_config.selector or None,
        stop_on_duplicates=True,
    )

    result = await async_paginate(
        page,
        config,
        extract_fn=_extract,
        base_url=workflow.start_url,
    )

    return result.records, result.stopped_reason


async def execute_workflow(workflow: Workflow) -> dict[str, Any]:
    """Execute a workflow and return extraction results.

    Args:
        workflow: The workflow to execute.

    Returns:
        A dict containing the extracted records, success flag, and metadata.
    """
    logger.info("Executing workflow %s (%s)", workflow.name, workflow.id)

    start_time = datetime.datetime.now(datetime.UTC)
    page = None
    context = None

    try:
        from app.browser_pool import get_browser_pool

        pool = get_browser_pool()
        domain = workflow.domain or "default"
        context = await pool.get_context(domain)
        page = await context.new_page()

        # Navigate to start URL
        try:
            await page.goto(workflow.start_url, wait_until="domcontentloaded", timeout=MAX_STEP_TIMEOUT_MS)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except (RuntimeError, OSError, TimeoutError):
                logger.debug("networkidle timeout during initial navigation")
            await asyncio.sleep(PAGE_SETTLE_SECONDS)
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("Failed to navigate to start URL: %s", exc)
            return {
                "workflow_id": workflow.id,
                "status": "failed",
                "error": f"Failed to load start URL: {exc}",
                "timestamp": start_time.isoformat(),
            }

        # Replay workflow steps
        timeline = await _replay_steps(page, workflow)

        # Handle pagination and extraction
        all_records, pagination_reason = await _paginate_and_extract(page, workflow)

        # Final page info
        try:
            final_url = page.url
            page_title = await page.title()
        except (RuntimeError, OSError, ValueError):
            final_url = workflow.start_url
            page_title = ""

        duration = (datetime.datetime.now(datetime.UTC) - start_time).total_seconds()

        return {
            "workflow_id": workflow.id,
            "status": "succeeded" if all_records or pagination_reason == "no_pagination" else "completed_empty",
            "records": all_records,
            "record_count": len(all_records),
            "timeline": timeline,
            "pagination_stopped_reason": pagination_reason,
            "final_url": final_url,
            "page_title": page_title,
            "duration_seconds": round(duration, 2),
            "timestamp": start_time.isoformat(),
        }

    except (RuntimeError, OSError, ValueError) as exc:
        logger.exception("Workflow execution failed for %s", workflow.id)
        return {
            "workflow_id": workflow.id,
            "status": "failed",
            "error": str(exc),
            "timestamp": start_time.isoformat(),
        }
    finally:
        if page is not None:
            try:
                await page.close()
            except (RuntimeError, OSError, ValueError):
                logger.debug("Failed to close Playwright page after workflow execution")


async def preview_workflow(workflow: Workflow) -> dict[str, Any]:
    """Preview a workflow by running a single-page test.

    Opens the start URL, replays steps, and returns sample data
    without full pagination.
    """
    logger.info("Previewing workflow %s (%s)", workflow.name, workflow.id)

    page = None
    context = None

    try:
        from app.browser_pool import get_browser_pool

        pool = get_browser_pool()
        domain = workflow.domain or "default"
        context = await pool.get_context(domain)
        page = await context.new_page()

        # Navigate to start URL
        await page.goto(workflow.start_url, wait_until="domcontentloaded", timeout=MAX_STEP_TIMEOUT_MS)
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=5000)
        await asyncio.sleep(PAGE_SETTLE_SECONDS)

        # Replay steps
        timeline = await _replay_steps(page, workflow)

        # Extract first page only (no pagination)
        sample_records = await _extract_records_from_page(page, workflow)
        sample_records = sample_records[:5]  # Limit to 5 for preview

        page_title = ""
        with contextlib.suppress(Exception):
            page_title = await page.title()

        return {
            "workflow_id": workflow.id,
            "preview_status": "succeeded",
            "sample_rows": sample_records,
            "record_count": len(sample_records),
            "timeline": timeline,
            "last_url": page.url if hasattr(page, "url") else workflow.start_url,
            "page_title": page_title,
            "warnings": [] if sample_records else ["No sample rows matched the extraction schema."],
        }

    except (RuntimeError, OSError, ValueError) as exc:
        logger.exception("Workflow preview failed for %s", workflow.id)
        return {
            "workflow_id": workflow.id,
            "preview_status": "failed",
            "error": str(exc),
            "message": "Preview failed. The start URL may be unreachable or the workflow steps may be invalid.",
        }
    finally:
        if page is not None:
            try:
                await page.close()
            except (RuntimeError, OSError, ValueError):
                logger.debug("Failed to close Playwright page after workflow preview")
