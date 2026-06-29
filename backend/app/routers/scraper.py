"""Scraper Router — endpoints for scraper observability, memory, configuration,
and diagnostics.

This router only exposes PRODUCT KERNEL endpoints. All research-backed routes
(trend analysis, economics, domain health alerts, ML selector optimization,
strategy evolution) have been quarantined to ``routers/experimental.py``
and require ``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true``.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.browser_pool import get_browser_pool
from app.config import settings
from app.models import (
    DomainConfidenceResponse,
    JobCreate,
    LowConfidenceSelectorItem,
    LowConfidenceSelectorsResponse,
    PreviewResponse,
    RegressionGenerateAllResponse,
    RegressionTestGenerateResponse,
    ScraperConfigResponse,
    ScraperDiagnosticsRequest,
    ScraperStatsResponse,
    SelectorCleanupResponse,
    SelectorMemoryFullStatsResponse,
    SelectorMemoryStatsResponse,
    StatusResponse,
)
from app.regression_capture import get_regression_capture
from app.scrape_telemetry import get_scrape_telemetry
from app.scraper_diagnostics import run_diagnostics
from app.selector_memory import get_selector_memory
from app.url_safety import validate_public_http_url
from app.utils.rbac import UserRole, require_role

router = APIRouter(prefix="/api/scraper", tags=["scraper"])
logger = logging.getLogger(__name__)


@router.get("/config", response_model=ScraperConfigResponse)
async def get_scraper_config(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return current scraper-related settings. Requires operator or admin."""
    return {
        "playwright_timeout": settings.PLAYWRIGHT_TIMEOUT,
        "page_settle_delay": settings.PAGE_SETTLE_DELAY,
        "request_timeout": settings.REQUEST_TIMEOUT,
        "max_retries": settings.MAX_RETRIES,
        "max_records_per_source": settings.MAX_RECORDS_PER_SOURCE,
        "selector_snippet_max_chars": settings.SELECTOR_SNIPPET_MAX_CHARS,
        "regex_max_containers": settings.REGEX_MAX_CONTAINERS,
    }


@router.get("/telemetry", response_model=list[dict])
async def get_recent_telemetry(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    n: int = 20,
):
    """Return the N most recent scrape telemetry events. Requires operator or admin."""
    return get_scrape_telemetry().get_recent(n)


@router.get("/memory/stats", response_model=SelectorMemoryStatsResponse)
async def get_selector_memory_brief(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return brief statistics on remembered selectors. Requires operator or admin."""
    memory = get_selector_memory()
    return SelectorMemoryStatsResponse(
        domain_count=len(memory._memory),
        total_successes=sum(e.get("success_count", 0) for e in memory._memory.values()),
        total_failures=sum(e.get("failure_count", 0) for e in memory._memory.values()),
        top_domains=sorted(
            [{"domain": d, "success": e.get("success_count", 0)} for d, e in memory._memory.items()],
            key=lambda x: x["success"],
            reverse=True,
        )[:10],
    )


@router.get("/browser", response_model=dict)
async def get_browser_stats(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return browser pool operational metrics. Requires operator or admin."""
    return get_browser_pool().get_metrics()


@router.get("/health/legacy", response_model=dict)
async def get_legacy_domain_health(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return health scores for all tracked domains (legacy crawl policy). Requires operator or admin."""
    from app.crawl_policy import get_crawl_policy

    policy = get_crawl_policy()
    states = policy.get_all_domain_states()

    health = {}
    for domain in states:
        if domain.startswith("_"):
            continue
        health[domain] = policy.get_domain_health_score(domain)

    return health


@router.get("/stats", response_model=ScraperStatsResponse)
async def get_scraper_stats(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return aggregated scraper performance statistics. Requires operator or admin."""
    telemetry = get_scrape_telemetry()
    recent_latency = telemetry.get_recent(10)
    recent_success = telemetry.get_recent(20)
    raw = telemetry.get_confidence_histogram()
    confidence_histogram = [[float(k.split("-")[0]), int(v)] for k, v in raw.items()] if raw else []
    return ScraperStatsResponse(
        confidence_histogram=confidence_histogram,
        recent_latency_avg=(
            sum(float(t.get("fetch_ms", 0) or 0) for t in recent_latency) / len(recent_latency) if recent_latency else 0
        ),
        recent_success_rate=(
            sum(1 for t in recent_success if not t.get("fallback_triggered", False)) / len(recent_success)
            if recent_success
            else 1.0
        ),
    )


@router.post("/screenshot", response_model=dict)
async def capture_screenshot(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    body: dict[str, Any],
):
    url = body.get("url", "")
    full_page = body.get("full_page", False)
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    try:
        validate_public_http_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"URL not allowed: {exc}") from exc
    from app.browser_pool import get_browser_pool
    pool = get_browser_pool()
    try:
        screenshot_b64 = await pool.capture_screenshot(url, full_page=full_page)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.exception("Screenshot capture failed for %s", url)
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {exc}") from exc
    return {"url": url, "screenshot": screenshot_b64, "full_page": full_page}


@router.delete("/telemetry", response_model=StatusResponse)
async def clear_telemetry(_role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))]):
    """Clear all scrape telemetry history."""
    get_scrape_telemetry().clear()
    return StatusResponse(status="ok")


@router.post("/diagnostics", response_model=dict)
async def get_scraper_diagnostics(
    req: ScraperDiagnosticsRequest,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Run a deep diagnostic scrape for a URL.

    Requires operator or admin role — triggers browser / network work.
    """
    # Defence-in-depth: reject SSRF targets (loopback, private RFC1918,
    # link-local, cloud-metadata, internal TLDs) before any outbound
    # call so the operator can't pivot to internal services.
    try:
        validate_public_http_url(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="URL not allowed for diagnostics") from exc
    try:
        report = await run_diagnostics(req.url, req.fields, min_record_score=req.min_score)
    except (RuntimeError, OSError, ValueError) as e:
        # Never leak internal error details; log server-side instead.
        logger.exception("Diagnostics run failed for %s", req.url)
        raise HTTPException(status_code=500, detail="Diagnostics run failed") from e
    return report.to_dict()


@router.post("/preview", response_model=PreviewResponse, response_model_exclude_none=True)
async def preview_extraction(
    req: JobCreate,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Dry-run an extraction without persisting a job (Roadmap Feat #19).

    Accepts the same ``JobCreate`` payload as job creation. Runs the
    extraction pipeline on the first URL only and returns sample results
    for inspection. No job is created, no data is stored.

    Useful for testing selectors, validating schemas, and previewing
    extraction quality before committing to a full job.
    """
    if not req.urls:
        raise HTTPException(status_code=400, detail="At least one URL is required for preview")

    valid_urls = []
    for url in req.urls[:1]:  # preview only the first URL
        try:
            validate_public_http_url(url)
            valid_urls.append(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid URL: {url}") from exc

    target_url = valid_urls[0]

    try:
        from app.scraper import scrape_url_attempt

        async def _run_preview():
            return await scrape_url_attempt(
                url=target_url,
                schema_fields=list(req.schema_fields),
                min_record_score=req.min_record_score,
                selectors_map=req.selectors_map or {},
                search_params=req.search_params,
                headers=req.headers or {},
                cookies=req.cookies or {},
            )

        result = await _run_preview()
        results = result if isinstance(result, list) else []
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.exception("Preview extraction failed for %s", target_url)
        raise HTTPException(status_code=500, detail=f"Preview extraction failed: {exc}") from exc

    # Return a sample (up to 10 records) without persisting
    preview_records = results[:10] if isinstance(results, list) else []
    return PreviewResponse(
        url=target_url,
        total_records_found=len(results) if isinstance(results, list) else 0,
        preview_records=preview_records,
        dry_run=True,
    )


# ─── Regression Capture (product kernel) ───────────────────────────────


@router.get("/regressions", response_model=dict)
async def get_regression_archive(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Return the regression capture archive — statistics and recent captures.

    Requires operator or admin.
    """
    try:
        capture = get_regression_capture()
        stats = await run_in_threadpool(capture.get_statistics)
        # Trim recent captures to the requested limit
        stats["recent_captures"] = stats.get("recent_captures", [])[:limit]
        return stats
    except (RuntimeError, OSError, ValueError) as e:
        logger.exception("Failed to get regression archive")
        raise HTTPException(status_code=500, detail="Failed to get regression archive") from e


@router.get("/regressions/{entry_id}", response_model=dict)
async def get_regression_detail(
    entry_id: str,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Return detailed information about a specific regression capture. Requires operator or admin."""
    try:
        capture = get_regression_capture()
        registry = await run_in_threadpool(capture.get_registry)
        for e in registry.entries:
            if e.id == entry_id:
                return {
                    "id": e.id,
                    "url": e.url,
                    "domain": e.domain,
                    "failure_category": e.failure_category,
                    "failure_confidence": e.failure_confidence,
                    "html_preview": e.html_preview[:500],
                    "html_size": e.html_size,
                    "captured_at": e.captured_at,
                    "schema_fields": e.schema_fields,
                    "fixture_filename": e.fixture_filename,
                    "has_replay_test": e.replay_test_generated,
                    "telemetry_snapshot": e.telemetry_snapshot,
                }
        raise HTTPException(status_code=404, detail=f"Regression entry not found: {entry_id}")
    except HTTPException:
        raise
    except (RuntimeError, OSError, ValueError) as e:
        logger.exception("Failed to get regression detail for entry %s", entry_id)
        raise HTTPException(status_code=500, detail="Failed to get regression detail") from e


@router.post("/regressions/{entry_id}/generate-test", response_model=RegressionTestGenerateResponse)
async def generate_regression_replay_test(
    entry_id: str,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Generate a pytest replay test for a captured regression."""
    try:
        capture = get_regression_capture()
        test_code = await run_in_threadpool(capture.generate_replay_test, entry_id)
        if test_code is None:
            raise HTTPException(
                status_code=404,
                detail=f"Regression entry not found or fixture missing: {entry_id}",
            )
        return RegressionTestGenerateResponse(entry_id=entry_id, test_code=test_code)
    except HTTPException:
        raise
    except (RuntimeError, OSError, ValueError) as e:
        logger.exception("Failed to generate regression replay test for entry %s", entry_id)
        raise HTTPException(status_code=500, detail="Failed to generate replay test") from e


@router.post("/regressions/generate-all-tests", response_model=RegressionGenerateAllResponse)
async def generate_all_replay_tests(_role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))]):
    """Generate replay tests for all captured regressions that lack one."""
    try:
        capture = get_regression_capture()
        all_tests = await run_in_threadpool(capture.generate_all_replay_tests)
        return RegressionGenerateAllResponse(
            total_tests_generated=all_tests.count("TEST SEPARATOR") + 1 if all_tests else 0,
            test_code=all_tests,
        )
    except (RuntimeError, OSError, ValueError) as e:
        logger.exception("Failed to generate all regression replay tests")
        raise HTTPException(status_code=500, detail="Failed to generate replay tests") from e


# ─── Selector Memory (product kernel) ─────────────────────────────────


@router.get("/selectors/stats", response_model=SelectorMemoryFullStatsResponse)
async def get_selector_memory_stats(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Get selector memory pool statistics.

    Returns aggregate statistics about cached selectors:
    - Total domains with cached selectors
    - Average confidence across all selectors
    - Distribution by confidence level
    - High / medium / low confidence counts

    Requires operator or admin.
    """
    selector_memory = get_selector_memory()
    stats = selector_memory.get_memory_stats()

    return SelectorMemoryFullStatsResponse(
        total_domains=stats["total_domains"],
        total_selectors=stats["total_selectors"],
        avg_confidence=round(stats["avg_confidence"], 3),
        high_confidence=stats["high_confidence"],
        medium_confidence=stats["medium_confidence"],
        low_confidence=stats["low_confidence"],
        confidence_distribution=stats["by_confidence"],
    )


@router.get("/selectors/domain/{domain}", response_model=DomainConfidenceResponse)
async def get_domain_selector_confidence(
    domain: str,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
):
    """Get selector confidence for a specific domain.

    Returns detailed confidence metrics:
    - Raw confidence (success rate)
    - Age factor (degradation over time)
    - Freshness factor (penalty for non-use)
    - Final confidence score
    - Reason (detailed explanation)

    Requires operator or admin.
    """
    # Validate domain is a plausible hostname (RFC 1035: max 253 chars,
    # only letters, digits, dots, hyphens, underscores). Reject giant
    # inputs, path separators, and injection characters that could sneak
    # into downstream URL construction.
    import re as _re

    _DOMAIN_RE = _re.compile(r"^[a-zA-Z0-9._-]{1,253}$")
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid domain: {domain!r} — must be 1-253 chars, only letters/digits/dots/hyphens/underscores",
        )
    selector_memory = get_selector_memory()

    # Create a fake URL to extract domain
    url = f"https://{domain}/"
    confidence = selector_memory.get_selector_confidence(url)

    if confidence is None:
        raise HTTPException(status_code=404, detail=f"No cached selectors for domain: {domain}")

    return DomainConfidenceResponse(
        domain=domain,
        raw_confidence=round(confidence.raw_confidence, 3),
        age_factor=round(confidence.age_factor, 3),
        freshness_factor=round(confidence.freshness_factor, 3),
        final_score=round(confidence.final_score, 3),
        reason=confidence.reason,
    )


@router.post("/selectors/cleanup", response_model=SelectorCleanupResponse)
async def trigger_selector_cleanup(_role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))]):
    """Manually trigger selector memory cleanup. Admin only.

    Forces deletion of all selectors below the confidence threshold,
    regardless of the normal cleanup interval.

    Returns cleanup statistics.
    """
    selector_memory = get_selector_memory()
    stats = await run_in_threadpool(selector_memory.force_cleanup)

    if not stats:
        return SelectorCleanupResponse(
            message="Cleanup not performed (too soon after last cleanup)",
            next_cleanup_available_in_seconds=86400,
        )

    return SelectorCleanupResponse(
        domains_checked=int(stats.get("domains_checked", 0)),
        selectors_deleted=int(stats.get("selectors_deleted", 0)),
        deleted_domains=len(stats.get("deleted_domains", [])),
        low_confidence_selectors=len(stats.get("low_confidence_selectors", [])),
    )


@router.get("/selectors/low-confidence", response_model=LowConfidenceSelectorsResponse)
async def get_low_confidence_selectors(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    threshold: Annotated[float, Query(ge=0, le=1)] = 0.5,
):
    """Get all selectors scoring below the specified threshold.

    Useful for identifying domains at risk of extraction failure.
    Requires operator or admin.
    """
    selector_memory = get_selector_memory()
    low_confidence: list[LowConfidenceSelectorItem] = []

    for domain, entry in selector_memory._memory.items():
        confidence = selector_memory._compute_confidence(entry)
        if confidence.final_score < threshold:
            low_confidence.append(
                LowConfidenceSelectorItem(
                    domain=domain,
                    score=round(confidence.final_score, 3),
                    raw_confidence=round(confidence.raw_confidence, 3),
                    age_factor=round(confidence.age_factor, 3),
                    freshness_factor=round(confidence.freshness_factor, 3),
                    success_count=entry.get("success_count", 0),
                    failure_count=entry.get("failure_count", 0),
                    reason=confidence.reason,
                ),
            )

    # Sort by score (worst first)
    low_confidence.sort(key=lambda x: x.score)

    return LowConfidenceSelectorsResponse(
        threshold=threshold,
        count=len(low_confidence),
        selectors=low_confidence,
    )
