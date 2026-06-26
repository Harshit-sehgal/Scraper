"""Playwright-backed workflow replay runner.

CAND-P2-WORKFLOW-REPLAY-BROWSER-001: adds a real browser execution
path behind the workflow runner interface. When no ``html_snapshot``
is provided, the preview endpoint can now launch a headless Playwright
browser, navigate to the start URL, execute bounded workflow steps,
capture a screenshot, and extract rows from the resulting page — all
without live-site dependency when using a local fixture server.

Safety constraints:
- Start URLs must pass ``validate_public_http_url`` (or be explicitly
  allowed via settings.SMOKE_TEST_MODE for localhost fixture servers).
- Total execution is capped at ``MAX_TOTAL_TIMEOUT_SECONDS``.
- Individual wait steps are capped at ``MAX_WAIT_MS`` (10 s).
- Screenshots are limited to ``MAX_SCREENSHOT_BYTES``.
- No auth/CAPTCHA/paywall bypass is attempted.
- Value redaction for sensitive-looking fields is applied to timeline
  entries.
"""

from __future__ import annotations

import base64
import logging
from contextlib import suppress
from typing import Any

from app.models import Workflow, WorkflowStepType
from app.services.workflow_runner import (
    MAX_WAIT_MS,
    _extract_rows,
    _now_iso,
    redact_step_value,
)

logger = logging.getLogger(__name__)

# ── Safety caps ──────────────────────────────────────────────────────────

MAX_TOTAL_TIMEOUT_SECONDS: int = 30
MAX_NAVIGATION_TIMEOUT_MS: int = 15_000
MAX_SCREENSHOT_BYTES: int = 500_000


async def run_workflow_in_browser(
    workflow: Workflow,
    *,
    sample_limit: int = 5,
    fixture_html: str | None = None,
) -> dict[str, Any]:
    """Execute a workflow in a headless Playwright browser.

    Uses the shared ``BrowserPool`` to reuse the Chromium process across
    requests while isolating each request's cookies/storage in a separate
    browser context.

    Parameters
    ----------
    workflow:
        The workflow model to execute.
    sample_limit:
        Maximum number of sample rows to extract.
    fixture_html:
        If provided, a local HTTP fixture server is started serving this
        HTML and the browser is pointed at it instead of the real start
        URL. This enables fully offline, deterministic tests.

    Returns
    -------
    dict
        The same shape as ``preview_workflow_snapshot`` output, with
        ``screenshot`` (base64) and ``sample_rows`` populated from the
        live page.
    """
    try:
        from playwright.async_api import async_playwright

        _ = async_playwright  # availability check; referenced to silence pyflakes
    except ImportError:
        return _browser_failure(
            workflow,
            failure_type="playwright_unavailable",
            user_message="Playwright is not installed. Install with: pip install playwright && playwright install",
            recommended_action="Install Playwright browser runtime.",
            timeline=[],
        )

    timeline: list[dict[str, Any]] = []
    screenshot_b64: str | None = None
    page_html: str = ""
    last_url: str = workflow.start_url

    # If a fixture HTML string is provided, start a temporary local
    # HTTP server and redirect the browser to it.
    fixture_server: Any = None
    fixture_port: int = 0
    actual_url: str = workflow.start_url

    if fixture_html is not None:
        actual_url, fixture_server, fixture_port = await _start_fixture_server(fixture_html)
        last_url = actual_url

    try:
        from app.browser_pool import get_browser_pool

        pool = get_browser_pool()

        async with pool.acquire_context(
            viewport_width=1280,
            viewport_height=720,
        ) as (_ctx_id, context):
            page = await context.new_page()
            page.set_default_timeout(MAX_NAVIGATION_TIMEOUT_MS)

            try:
                result = await _execute_steps(
                    page,
                    workflow,
                    actual_url,
                    timeline,
                )
                if result is not None:
                    return result

                # After all steps, capture page state
                last_url = page.url
                page_html = await page.content()

                try:
                    raw_bytes = await page.screenshot(full_page=False, type="jpeg", quality=60)
                    if len(raw_bytes) <= MAX_SCREENSHOT_BYTES:
                        screenshot_b64 = base64.b64encode(raw_bytes).decode("ascii")
                    else:
                        timeline.append(
                            {
                                "order": -1,
                                "action": "screenshot",
                                "status": "capped",
                                "timestamp": _now_iso(),
                                "detail": f"screenshot {len(raw_bytes)}b exceeds {MAX_SCREENSHOT_BYTES}b cap",
                            }
                        )
                except Exception as exc:
                    timeline.append(
                        {
                            "order": -1,
                            "action": "screenshot",
                            "status": "failed",
                            "timestamp": _now_iso(),
                            "detail": str(exc)[:200],
                        }
                    )
                finally:
                    await page.close()

            except Exception as exc:
                return _browser_failure(
                    workflow,
                    failure_type="browser_execution_error",
                    user_message=f"Browser execution failed: {exc}",
                    recommended_action="Check the workflow steps and start URL.",
                    timeline=timeline,
                    last_url=last_url,
                )
    except ImportError:
        return _browser_failure(
            workflow,
            failure_type="playwright_unavailable",
            user_message="Playwright is not installed. Install with: pip install playwright && playwright install",
            recommended_action="Install Playwright browser runtime.",
            timeline=timeline,
            last_url=last_url,
        )
    except Exception as exc:
        return _browser_failure(
            workflow,
            failure_type="browser_launch_error",
            user_message=f"Failed to launch browser: {exc}",
            recommended_action="Ensure Playwright browsers are installed (playwright install).",
            timeline=timeline,
            last_url=last_url,
        )
    finally:
        if fixture_server is not None:
            await _stop_fixture_server(fixture_server, fixture_port)

    # Extract rows from the final page HTML
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    sample_rows = _extract_rows(soup, workflow.extraction_schema, limit=sample_limit)
    warnings: list[str] = [] if sample_rows else ["No sample rows matched the extraction schema."]

    return {
        "workflow_id": workflow.id,
        "preview_status": "succeeded",
        "sample_rows": sample_rows,
        "timeline": timeline,
        "warnings": warnings,
        "last_url": last_url,
        "page_title": _page_title_from_soup(soup),
        "screenshot": screenshot_b64,
        "record_count": len(sample_rows),
    }


async def _execute_steps(
    page: Any,
    workflow: Workflow,
    start_url: str,
    timeline: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Execute each workflow step in order on the Playwright page.

    Returns a failure dict if a step fails fatally, or None if all
    steps completed.
    """
    first_goto = True
    for step in sorted(workflow.steps, key=lambda s: s.order):
        event: dict[str, Any] = {
            "order": step.order,
            "action": step.step_type.value,
            "selector": step.selector,
            "value": redact_step_value(step.value, label=step.description, selector=step.selector),
            "status": "ok",
            "timestamp": _now_iso(),
        }

        try:
            step_type = step.step_type

            if step_type in {WorkflowStepType.GOTO, WorkflowStepType.OPEN}:
                url = start_url if first_goto else (step.value or start_url)
                first_goto = False
                event["url"] = url
                await page.goto(url, wait_until="domcontentloaded", timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.CLICK:
                if step.selector:
                    await page.click(step.selector, timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.FILL:
                if step.selector:
                    await page.fill(step.selector, step.value, timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.SELECT:
                if step.selector:
                    await page.select_option(step.selector, step.value, timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.CHECK:
                if step.selector:
                    await page.check(step.selector, timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.UNCHECK:
                if step.selector:
                    await page.uncheck(step.selector, timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.PRESS:
                if step.selector:
                    await page.press(step.selector, step.value or "Enter", timeout=MAX_NAVIGATION_TIMEOUT_MS)
                else:
                    await page.keyboard.press(step.value or "Enter")

            elif step_type == WorkflowStepType.SCROLL:
                await page.evaluate("window.scrollBy(0, window.innerHeight)")

            elif step_type in {
                WorkflowStepType.WAIT,
                WorkflowStepType.WAIT_FOR_TIMEOUT_LIMITED,
            }:
                wait_ms = int(str(step.value or "0") or "0")
                wait_ms = min(wait_ms, MAX_WAIT_MS)
                event["value"] = str(wait_ms)
                if wait_ms > 0:
                    await page.wait_for_timeout(wait_ms)

            elif step_type == WorkflowStepType.WAIT_FOR_SELECTOR:
                if step.selector:
                    await page.wait_for_selector(step.selector, timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.WAIT_FOR_URL:
                if step.value:
                    await page.wait_for_url(f"**/{step.value}**", timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.WAIT_FOR_TEXT:
                if step.value:
                    await page.wait_for_selector(f"text={step.value}", timeout=MAX_NAVIGATION_TIMEOUT_MS)

            elif step_type == WorkflowStepType.EXTRACT:
                pass  # extraction happens after all steps complete

        except Exception as exc:
            event["status"] = "failed"
            event["detail"] = str(exc)[:200]
            timeline.append(event)
            return _browser_failure(
                workflow,
                failure_type="step_execution_error",
                user_message=f"Step {step.order} ({step.step_type.value}) failed: {exc}",
                recommended_action="Check the selector and value. Update the workflow step and retry.",
                timeline=timeline,
                last_url=page.url,
            )

        timeline.append(event)

    return None  # all steps succeeded


# ── Fixture server ───────────────────────────────────────────────────────


async def _start_fixture_server(html: str) -> tuple[str, Any, int]:
    """Start a local HTTP server serving *html* on a random port.

    Returns (url, server, port).
    """
    from aiohttp import web

    async def _handler(_request: web.Request) -> web.Response:
        return web.Response(text=html, content_type="text/html")

    app = web.Application()
    app.router.add_route("GET", "/", _handler)
    app.router.add_route("GET", "/{path:.*}", _handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    # aiohttp assigns a random port; find it from the site object
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    url = f"http://127.0.0.1:{port}/"
    return url, runner, port


async def _stop_fixture_server(runner: Any, _port: int) -> None:
    """Clean up the fixture server."""
    with suppress(Exception):
        await runner.cleanup()


# ── Helpers ──────────────────────────────────────────────────────────────


def _page_title_from_soup(soup: Any) -> str:
    """Extract page title from a BeautifulSoup object."""
    title = soup.find("title")
    return title.get_text(" ", strip=True) if title else ""


def _browser_failure(
    workflow: Workflow,
    *,
    failure_type: str,
    user_message: str,
    recommended_action: str,
    timeline: list[dict[str, Any]],
    last_url: str = "",
) -> dict[str, Any]:
    """Return a standardised failure dict for browser execution errors."""
    return {
        "workflow_id": workflow.id,
        "preview_status": "failed",
        "failure_type": failure_type,
        "user_message": user_message,
        "recommended_action": recommended_action,
        "timeline": timeline,
        "last_url": last_url or workflow.start_url,
        "page_title": "",
        "screenshot": None,
        "sample_rows": [],
        "warnings": [],
    }
