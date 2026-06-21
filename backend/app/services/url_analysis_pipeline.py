"""URL Analysis Pipeline — stage-oriented orchestration for URL field discovery.

Extracts the numbered stages from ``selector_discovery.analyze_url_for_fields``
into focused stage methods on a ``URLAnalysisPipeline`` class. The pipeline
is stateful: a ``_UrlAnalysisContext`` dataclass flows through the stages.

All stage methods use lazy imports through ``app.selector_discovery`` so that
existing test mocks on ``app.selector_discovery.*`` continue to work.

Usage::

    pipeline = URLAnalysisPipeline()
    result = await pipeline.run(url, search_params=None, acquisition_mode="standard")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ── Lazy import helpers ──────────────────────────────────────────────────


def _import_sd(name: str):
    """Lazy-import a name from app.selector_discovery.

    This indirection ensures that test mocks patching
    ``app.selector_discovery.<name>`` are picked up at call time.
    """
    import importlib

    mod = importlib.import_module("app.selector_discovery")
    return getattr(mod, name)


# ── Pipeline context ─────────────────────────────────────────────────────


@dataclass
class _UrlAnalysisContext:
    """Mutable context that flows through pipeline stages."""

    # Inputs
    url: str
    search_params: dict[str, str] | None = None
    acquisition_mode: str = "standard"

    # Stage outputs
    final_url: str = ""
    redirect_info: dict = field(default_factory=dict)
    session_detection: dict = field(default_factory=dict)
    html: str = ""
    fetch_method: str = "unknown"
    search_form: dict = field(default_factory=lambda: {"detected": False, "form_fields": [], "search_fields": [], "action": ""})
    search_recovery: dict | None = None
    anti_bot_score: float = 0.0
    profile: Any = None
    patterns: Any = None
    content_quality: dict = field(default_factory=dict)
    empty_check: Any = None
    suggested_fields: list = field(default_factory=list)
    estimated_records: int = 0
    item_container: str = ""
    browser_state_evidence: Any = None
    escalated_mode: str | None = None

    # The acquisition state value (StrEnum value) from the built lineage.
    # Used by the escalation check after _stage_build_response completes.
    _acquisition_state_value: str = "direct"

    # Timing
    start_time: float = field(default_factory=time.time)
    elapsed: float = 0.0

    # Error state
    error_response: dict | None = None

    # Set in run().
    config: Any = None
    mode_enum: Any = None


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════


class URLAnalysisPipeline:
    """Stage-oriented URL analysis pipeline.

    Each pipeline stage is a method that receives and mutates the shared
    ``_UrlAnalysisContext``. The ``run`` method orchestrates the stages
    in order, handling early returns and recursive escalation.
    """

    async def run(
        self,
        url: str,
        search_params: dict[str, str] | None = None,
        acquisition_mode: str = "standard",
        _escalation_depth: int = 0,
    ) -> dict[str, Any]:
        """Execute the full URL analysis pipeline.

        Args:
            url: The URL to analyze.
            search_params: Optional search params for session recovery.
            acquisition_mode: The acquisition mode (standard, etc.).
            _escalation_depth: Internal — tracks retry depth.

        Returns:
            Analysis result dict with suggested_fields, page_structure, etc.
        """
        ctx = _UrlAnalysisContext(
            url=url,
            search_params=search_params,
            acquisition_mode=acquisition_mode,
            start_time=time.time(),
        )

        _import_sd("reset_llm_call_count")()

        # Resolve acquisition config
        from app.acquisition_mode import (  # research-shell, lazy
            AcquisitionConfig,
            AcquisitionMode,
            escalate_mode,
            should_escalate,
        )

        try:
            ctx.mode_enum = AcquisitionMode(acquisition_mode)
        except ValueError:
            ctx.mode_enum = AcquisitionMode.STANDARD
        ctx.config = AcquisitionConfig.from_mode(ctx.mode_enum)

        logger.info("[URLAnalyzer] Fetching and analyzing: %s", url)

        # ── Stage 1: URL Resolution ──────────────────────────────────
        await self._stage_resolve_url(ctx)
        ctx.redirect_info = _import_sd("_detect_redirect")(url, ctx.final_url)

        # ── Stage 2: Session Detection ───────────────────────────────
        await self._stage_detect_session(ctx)

        # ── Stage 3: Page Fetching ───────────────────────────────────
        fetch_ok = await self._stage_fetch_page(ctx)
        if not fetch_ok:
            if ctx.error_response is None:
                msg = "fetch stage failed without an error response"
                raise RuntimeError(msg)
            return ctx.error_response

        # ── Stage 4: Search Form Recovery ────────────────────────────
        await self._stage_search_recovery(ctx)

        # ── Stage 5: Page Analysis ───────────────────────────────────
        self._stage_analyze_page(ctx)

        # ── Stage 6: Content Quality + Empty Check ───────────────────
        self._stage_quality_check(ctx)

        # ── Stage 7: Field Extraction (LLM) ──────────────────────────
        await self._stage_extract_fields(ctx)

        # ── Stage 8: Response Building ───────────────────────────────
        response = await self._stage_build_response(ctx)

        # ── Escalation Check ─────────────────────────────────────────
        max_depth = ctx.config.max_retries
        if _escalation_depth < max_depth and should_escalate(
            ctx.mode_enum, ctx._acquisition_state_value, ctx.empty_check.is_empty
        ):
            escalated_mode = escalate_mode(ctx.mode_enum)
            if escalated_mode != ctx.mode_enum:
                logger.info(
                    "[URLAnalyzer] Escalating from %s → %s (depth %d)",
                    ctx.mode_enum.value,
                    escalated_mode.value,
                    _escalation_depth + 1,
                )
                return await self.run(
                    url=url,
                    search_params=search_params,
                    acquisition_mode=escalated_mode.value,
                    _escalation_depth=_escalation_depth + 1,
                )

        return response

    # ── Stage 1: URL Resolution ──────────────────────────────────────────

    async def _stage_resolve_url(self, ctx: _UrlAnalysisContext) -> None:
        """Resolve the final URL via httpx redirect-following with SSRF checks."""
        from urllib.parse import urljoin

        import httpx

        from app.url_safety import get_safe_async_client, validate_public_http_url

        ctx.final_url = ctx.url
        try:
            async with get_safe_async_client(
                follow_redirects=False,
                timeout=httpx.Timeout(10.0),
            ) as client:
                resp = await client.get(ctx.url, follow_redirects=False)

                max_hops = 10
                hops = 0
                while resp.is_redirect and hops < max_hops:
                    hops += 1
                    location = resp.headers.get("location", "")
                    if not location:
                        break
                    redirect_target = urljoin(str(resp.url), location)
                    try:
                        validate_public_http_url(redirect_target)
                    except ValueError as e:
                        logger.warning(
                            "[URLAnalyzer] Redirect target blocked by SSRF validation: %s -> %s: %s",
                            ctx.url,
                            redirect_target,
                            e,
                        )
                        break
                    resp = await client.get(redirect_target, follow_redirects=False)

                if str(resp.url) != ctx.url:
                    ctx.final_url = str(resp.url)
                    logger.info(
                        "[URLAnalyzer] URL resolved: %s -> %s (after %d redirect hops)",
                        ctx.url,
                        ctx.final_url,
                        hops,
                    )
        except Exception as exc:
            logger.debug("[URLAnalyzer] Could not determine final URL via httpx for %s: %s", ctx.url, exc, exc_info=True)

    # ── Stage 2: Session Detection ───────────────────────────────────────

    async def _stage_detect_session(self, ctx: _UrlAnalysisContext) -> None:
        """Detect session-bound URL parameters."""
        detect = _import_sd("detect_session_params")
        if ctx.config.detect_session_params:
            ctx.session_detection = detect(ctx.url)
        else:
            ctx.session_detection = {
                "is_session_bound": False,
                "ephemeral_params": [],
                "canonical_url": ctx.url,
                "confidence": 0.0,
                "details": [],
            }

    # ── Stage 3: Page Fetching ───────────────────────────────────────────

    async def _stage_fetch_page(self, ctx: _UrlAnalysisContext) -> bool:
        """Fetch the page HTML via Playwright.

        Returns False if fetch failed or page is empty (error response set).
        """
        from app.html_utils import fetch_page_content
        from app.strategy_evolution import FetchStrategy  # research-shell, lazy

        try:
            html, _js_render_delay, fetch_method, _retry_count = await fetch_page_content(
                ctx.url,
                preferred_method=FetchStrategy.PLAYWRIGHT_FULL,
            )
            ctx.html = html
            ctx.fetch_method = fetch_method
        except Exception as e:
            logger.exception("[URLAnalyzer] Failed to fetch %s", ctx.url)
            ctx.error_response = self._build_error_response(
                ctx,
                error_message=f"Failed to fetch URL: {e!s}",
                user_message=f"Failed to fetch the URL: {e!s}",
            )
            return False

        if not ctx.html or len(ctx.html.strip()) < 100:
            ctx.error_response = self._build_error_response(
                ctx,
                error_message="Fetched page appears empty",
                user_message="The fetched page appears to be empty.",
                empty_type="blank",
                suggestions=["The URL may be incorrect or the server returned an empty page"],
            )
            return False

        return True

    # ── Stage 4: Search Form Recovery ────────────────────────────────────

    async def _stage_search_recovery(self, ctx: _UrlAnalysisContext) -> None:
        """Attempt search form recovery for expired session URLs."""
        detect_form = _import_sd("_detect_search_form")
        try_recovery = _import_sd("_try_form_search_recovery")
        build_redirect = _import_sd("build_redirect_info")

        if ctx.config.attempt_search_form:
            ctx.search_form = detect_form(ctx.html)
        else:
            ctx.search_form = {"detected": False, "form_fields": [], "search_fields": [], "action": ""}
        ctx.search_recovery = None

        if (
            ctx.config.attempt_recovery
            and ctx.redirect_info.get("redirected")
            and ctx.search_params
            and ctx.search_form.get("detected")
        ):
            logger.info(
                "[URLAnalyzer] Redirected URL with search params attempting recovery via %s",
                ctx.search_form.get("action", "/search"),
            )
            ctx.search_recovery = await try_recovery(
                landing_page_html=ctx.html,
                landing_page_url=ctx.final_url,
                search_params=ctx.search_params,
            )

            if ctx.search_recovery.get("success") and ctx.search_recovery.get("fresh_html"):
                logger.info(
                    "[URLAnalyzer] Recovery succeeded -> %s, re-analyzing fresh page",
                    ctx.search_recovery.get("fresh_url", ""),
                )
                ctx.html = ctx.search_recovery["fresh_html"]
                ctx.fetch_method = "search_form_post"
                if ctx.search_recovery.get("fresh_url"):
                    ctx.final_url = ctx.search_recovery["fresh_url"]
                ctx.redirect_info = build_redirect(
                    original_url=ctx.url,
                    final_url=ctx.final_url,
                    search_recovery=ctx.search_recovery,
                    search_form=ctx.search_form,
                    search_params=ctx.search_params,
                    fetch_method=ctx.fetch_method,
                    existing_redirect_info=ctx.redirect_info,
                )
        elif ctx.redirect_info.get("redirected") and ctx.search_form.get("detected"):
            logger.info(
                "[URLAnalyzer] Redirected URL with search form detected provide search_params to attempt recovery",
            )

    # ── Stage 5: Page Analysis ───────────────────────────────────────────

    def _stage_analyze_page(self, ctx: _UrlAnalysisContext) -> None:
        """Analyze page structure, value patterns, and anti-bot score."""
        from app.scrape_telemetry import detect_anti_bot

        ctx.anti_bot_score = detect_anti_bot(ctx.html)
        ctx.profile = _import_sd("detect_page_structure")(ctx.html)
        ctx.patterns = _import_sd("detect_value_patterns")(ctx.html)

    # ── Stage 6: Content Quality + Empty Check ───────────────────────────

    def _stage_quality_check(self, ctx: _UrlAnalysisContext) -> None:
        """Content quality assessment and empty response detection."""
        assess = _import_sd("_assess_content_quality")
        detect_empty = _import_sd("detect_empty_response")
        echeck_cls = _import_sd("EmptyResponseCheck")

        ctx.content_quality = assess(ctx.html, ctx.profile)
        ctx.empty_check = (
            detect_empty(ctx.html)
            if ctx.config.detect_empty_responses
            else echeck_cls(is_empty=False, empty_type="", confidence=0.0, message="Empty response detection disabled")
        )

    # ── Stage 7: Field Extraction (LLM) ──────────────────────────────────

    async def _stage_extract_fields(self, ctx: _UrlAnalysisContext) -> None:
        """Extract container values, run LLM analysis, build field suggestions."""
        extract_values = _import_sd("_extract_container_text_values")
        rename_fields = _import_sd("_rename_generic_fields")
        build_prompt = _import_sd("build_url_analysis_prompt")
        build_llm = _import_sd("_build_llm_fields")
        llm_json = _import_sd("llm_json")
        from bs4 import BeautifulSoup

        container_values = extract_values(ctx.html, ctx.profile.container_selector)

        if len(container_values) < 3:
            soup = BeautifulSoup(ctx.html, "html.parser")
            for noise in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
                noise.decompose()
            visible_text = soup.get_text(separator=" ", strip=True)
            chunks = []
            for tok in visible_text.split():
                tok = tok.strip()
                if tok and len(tok) > 1 and len(tok) < 80 and tok not in chunks:
                    chunks.append(tok)
            container_values = chunks[:40]

        page_analysis = {
            "structure_type": ctx.profile.structure_type,
            "structure_confidence": ctx.profile.structure_confidence,
            "headers": ctx.profile.headers,
        }

        prompt = build_prompt(container_values, page_analysis)

        try:
            result = await llm_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You output valid JSON objects for data schema design. No markdown, no commentary. Return ONLY the JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=settings.URL_ANALYZER_TEMPERATURE,
                timeout=settings.LLM_SELECTOR_TIMEOUT,
            )
        except Exception:
            logger.exception("[URLAnalyzer] LLM analysis failed for %s", ctx.url)
            result = None

        ctx.suggested_fields = rename_fields(build_llm(result, ctx.patterns))
        ctx.suggested_fields.sort(key=lambda f: f["confidence"], reverse=True)
        ctx.suggested_fields = ctx.suggested_fields[: settings.URL_ANALYZER_MAX_FIELDS]

        ctx.item_container = ctx.profile.container_selector
        ctx.estimated_records = 0
        if result and isinstance(result, dict):
            ctx.estimated_records = int(result.get("estimated_record_count", 0))

    # ── Stage 8: Response Building ───────────────────────────────────────

    async def _stage_build_response(self, ctx: _UrlAnalysisContext) -> dict[str, Any]:
        """Build the final response with acquisition lineage and telemetry."""
        from app.acquisition_state import AcquisitionLineage, AcquisitionState

        ctx.elapsed = time.time() - ctx.start_time

        # Log with redirect / quality / recovery context
        quality_warning = ""
        if ctx.redirect_info.get("redirected"):
            quality_warning = f" [REDIRECTED: {ctx.redirect_info.get('redirect_type', 'unknown')}]"
        if ctx.content_quality.get("quality") != "good":
            quality_warning += f" [QUALITY: {ctx.content_quality.get('quality', 'unknown')}]"
        if ctx.search_recovery and ctx.search_recovery.get("success"):
            quality_warning += " [RECOVERED via search form]"
        logger.info(
            "[URLAnalyzer] Analyzed %s: %s structure, %d fields suggested, %.1fs%s",
            ctx.url if not ctx.search_recovery else ctx.search_recovery.get("fresh_url", ctx.url),
            ctx.profile.structure_type,
            len(ctx.suggested_fields),
            ctx.elapsed,
            quality_warning,
        )

        # Build acquisition lineage
        acquisition_lineage = AcquisitionLineage.from_redirect_info(
            redirect_info=ctx.redirect_info,
            original_url=ctx.url,
            final_url=ctx.final_url,
            fetch_method=ctx.fetch_method,
            search_recovery=ctx.search_recovery,
            search_form=ctx.search_form or None,
            search_params=ctx.search_params,
        )
        acquisition_lineage.session_bound = bool(ctx.session_detection.get("is_session_bound", False))
        acquisition_lineage.ephemeral_params = list(ctx.session_detection.get("ephemeral_params") or [])

        has_containers = bool(ctx.content_quality.get("has_data_containers"))
        not_empty_score = 0.5 if not ctx.empty_check.is_empty else 0.0
        data_score = (1.0 if has_containers else 0.0) + not_empty_score - ctx.anti_bot_score * 0.3
        acquisition_lineage.data_evidence_score = round(data_score, 3) / 1.5
        acquisition_lineage.anti_bot_score = round(ctx.anti_bot_score, 3)
        acquisition_lineage.containers_detected = ctx.content_quality.get("data_container_count", 0)
        acquisition_lineage.forms_detected = 1 if (ctx.search_form or {}).get("detected") else 0

        from app.browser_network_capture import get_browser_state, get_captures

        ctx.browser_state_evidence = get_browser_state(ctx.url)
        acquisition_lineage.network_payloads_found = len(get_captures(ctx.url))

        if not acquisition_lineage.recommended_next_action:
            if ctx.empty_check.is_empty and ctx.anti_bot_score > 0.5:
                acquisition_lineage.recommended_next_action = "try_browser_mode_or_search_params"
            elif ctx.session_detection.get("is_session_bound"):
                acquisition_lineage.recommended_next_action = "provide_search_params"
            elif not ctx.content_quality.get("has_data_containers"):
                acquisition_lineage.recommended_next_action = "try_deep_scan_mode"

        if ctx.empty_check.is_empty and acquisition_lineage.state == AcquisitionState.DIRECT:
            acquisition_lineage.state = AcquisitionState.EMPTY_RESPONSE
            acquisition_lineage.message = ctx.empty_check.message

        canonical_url = ctx.session_detection["canonical_url"]
        if acquisition_lineage.state == AcquisitionState.RECOVERED and acquisition_lineage.recovered_url:
            canonical_url = acquisition_lineage.recovered_url

        # Store the acquisition state value for the escalation check
        ctx._acquisition_state_value = acquisition_lineage.state.value

        # Record telemetry
        try:
            from app.acquisition_telemetry import get_acquisition_telemetry

            get_acquisition_telemetry().record(
                url=ctx.url,
                state=acquisition_lineage.state,
                original_url=acquisition_lineage.original_url,
                final_url=acquisition_lineage.final_url,
                canonical_url=canonical_url,
                fetch_method=ctx.fetch_method,
                session_bound=bool(ctx.session_detection.get("is_session_bound", False)),
                ephemeral_params=list(ctx.session_detection.get("ephemeral_params") or []),
                recovery_method=acquisition_lineage.recovery_method,
                recovered_url=acquisition_lineage.recovered_url,
                fetch_time_ms=round((time.time() - ctx.start_time) * 1000, 1),
            )
        except Exception:
            logger.debug("[URLAnalyzer] Failed to record acquisition telemetry", exc_info=True)

        return {
            "url": ctx.url,
            "redirect_info": ctx.redirect_info,
            "acquisition_lineage": acquisition_lineage.model_dump(mode="json"),
            "user_message": acquisition_lineage.get_user_message(),
            "session_detection": ctx.session_detection,
            "canonical_url": canonical_url,
            "acquisition_mode": ctx.acquisition_mode,
            "acquisition_config": {
                "mode": ctx.config.mode.value,
                "attempt_recovery": ctx.config.attempt_recovery,
                "attempt_search_form": ctx.config.attempt_search_form,
                "use_playwright": ctx.config.use_playwright,
                "detect_empty_responses": ctx.config.detect_empty_responses,
                "detect_session_params": ctx.config.detect_session_params,
                "max_retries": ctx.config.max_retries,
                "escalated": ctx.escalated_mode is not None,
            },
            "content_quality": ctx.content_quality,
            "empty_check": {
                "is_empty": ctx.empty_check.is_empty,
                "empty_type": ctx.empty_check.empty_type,
                "confidence": ctx.empty_check.confidence,
                "message": ctx.empty_check.message,
                "suggestions": ctx.empty_check.suggestions,
            },
            "search_form": ctx.search_form if ctx.search_form.get("detected") else None,
            "search_recovery": ctx.search_recovery,
            "page_structure": ctx.profile.structure_type,
            "structure_confidence": ctx.profile.structure_confidence,
            "estimated_record_count": ctx.estimated_records,
            "item_container": ctx.item_container,
            "fetch_method": ctx.fetch_method,
            "fetch_time_ms": round((time.time() - ctx.start_time) * 1000, 1),
            "anti_bot_score": round(ctx.anti_bot_score, 3),
            "browser_state_evidence": ctx.browser_state_evidence,
            "suggested_fields": ctx.suggested_fields,
        }

    # ── Error Response Builder ───────────────────────────────────────────

    def _build_error_response(
        self,
        ctx: _UrlAnalysisContext,
        *,
        error_message: str,
        user_message: str,
        empty_type: str = "blank",
        suggestions: list[str] | None = None,
    ) -> dict:
        """Build a consistent error response for early-return paths."""
        from app.acquisition_state import AcquisitionLineage, AcquisitionState

        lineage = AcquisitionLineage(
            original_url=ctx.url,
            final_url=ctx.final_url,
            state=AcquisitionState.DIRECT,
            message=error_message,
        )

        return {
            "url": ctx.url,
            "redirect_info": ctx.redirect_info,
            "acquisition_lineage": lineage.model_dump(mode="json"),
            "user_message": user_message,
            "session_detection": ctx.session_detection,
            "canonical_url": ctx.session_detection.get("canonical_url", ctx.url),
            "content_quality": None,
            "empty_check": {
                "is_empty": True,
                "empty_type": empty_type,
                "confidence": 1.0,
                "message": error_message,
                "suggestions": suggestions or [],
            },
            "search_form": None,
            "search_recovery": None,
            "error": error_message,
            "page_structure": "unknown",
            "structure_confidence": 0.0,
            "estimated_record_count": 0,
            "item_container": None,
            "suggested_fields": [],
            "anti_bot_score": 0.0,
            "acquisition_mode": ctx.acquisition_mode,
        }
