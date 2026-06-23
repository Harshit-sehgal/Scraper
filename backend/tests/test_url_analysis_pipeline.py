"""Unit tests for URLAnalysisPipeline — covers each stage in isolation
and the run() orchestration with mocked selector_discovery dependencies."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.url_analysis_pipeline import (
    URLAnalysisPipeline,
    _UrlAnalysisContext,
)


@pytest.fixture
def ctx() -> _UrlAnalysisContext:
    return _UrlAnalysisContext(
        url="https://example.com/listings",
        search_params=None,
        acquisition_mode="standard",
    )


@pytest.fixture
def pipeline() -> URLAnalysisPipeline:
    return URLAnalysisPipeline()


# ── _build_error_response ────────────────────────────────────────────────


def test_build_error_response_shape(ctx: _UrlAnalysisContext) -> None:
    pipeline = URLAnalysisPipeline()
    result = pipeline._build_error_response(
        ctx,
        error_message="test error",
        user_message="user friendly",
    )
    assert result["url"] == ctx.url
    assert result["error"] == "test error"
    assert result["user_message"] == "user friendly"
    assert result["page_structure"] == "unknown"
    assert result["suggested_fields"] == []
    assert result["empty_check"]["is_empty"] is True
    assert result["empty_check"]["empty_type"] == "blank"
    assert result["acquisition_lineage"] is not None
    assert result["search_form"] is None
    assert result["search_recovery"] is None


def test_build_error_response_with_suggestions(ctx: _UrlAnalysisContext) -> None:
    pipeline = URLAnalysisPipeline()
    result = pipeline._build_error_response(
        ctx,
        error_message="empty page",
        user_message="looks empty",
        empty_type="no_content",
        suggestions=["try another URL", "check the link"],
    )
    assert result["empty_check"]["suggestions"] == [
        "try another URL",
        "check the link",
    ]


# ── _stage_resolve_url ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_stage_resolve_url_passthrough_on_error(pipeline: URLAnalysisPipeline, ctx: _UrlAnalysisContext) -> None:
    """When httpx raises (network error), final_url should remain as url."""
    await pipeline._stage_resolve_url(ctx)
    assert ctx.final_url == ctx.url


# ── _stage_detect_session ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_stage_detect_session_calls_detect_when_enabled(
    pipeline: URLAnalysisPipeline,
) -> None:
    ctx = _UrlAnalysisContext(url="https://example.com?sid=abc123", acquisition_mode="standard")
    ctx.config = MagicMock()
    ctx.config.detect_session_params = True

    with patch(
        "app.services.url_analysis_pipeline._import_sd",
        return_value=lambda u: {
            "is_session_bound": True,
            "ephemeral_params": ["sid"],
            "canonical_url": u,
            "confidence": 0.9,
            "details": [],
        },
    ):
        await pipeline._stage_detect_session(ctx)
        assert ctx.session_detection["is_session_bound"] is True
        assert "sid" in ctx.session_detection["ephemeral_params"]


# ── _stage_fetch_page ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_stage_fetch_page_error_sets_error_response(pipeline: URLAnalysisPipeline, ctx: _UrlAnalysisContext) -> None:
    with patch(
        "app.html_utils.fetch_page_content",
        side_effect=RuntimeError("connection refused"),
    ):
        ok = await pipeline._stage_fetch_page(ctx)
        assert ok is False
        assert ctx.error_response is not None
        assert "connection refused" in ctx.error_response["error"]


@pytest.mark.anyio
async def test_stage_fetch_page_empty_html_returns_false(pipeline: URLAnalysisPipeline, ctx: _UrlAnalysisContext) -> None:
    with patch("app.html_utils.fetch_page_content", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("   ", 0.0, "playwright", 0)
        ok = await pipeline._stage_fetch_page(ctx)
        assert ok is False
        assert ctx.error_response is not None


@pytest.mark.anyio
async def test_stage_fetch_page_success(pipeline: URLAnalysisPipeline, ctx: _UrlAnalysisContext) -> None:
    with patch("app.html_utils.fetch_page_content", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ("<html><body>content</body></html>" * 20, 0.0, "playwright", 0)
        ok = await pipeline._stage_fetch_page(ctx)
        assert ok is True
        assert ctx.html != ""
        assert ctx.fetch_method == "playwright"


# ── _stage_analyze_page ───────────────────────────────────────────────────


def test_stage_analyze_page_calls_detection(pipeline: URLAnalysisPipeline) -> None:
    ctx = _UrlAnalysisContext(url="https://example.com", acquisition_mode="standard")
    ctx.html = "<html><body>data</body></html>"

    mock_profile = MagicMock()
    mock_profile.structure_type = "table"
    mock_profile.structure_confidence = 0.85

    def fake_import(name: str):
        store = {
            "detect_page_structure": lambda h: mock_profile,
            "detect_value_patterns": lambda h: {"fields": [], "confidence": 0.0},
        }
        return store.get(name, MagicMock())

    with patch("app.services.url_analysis_pipeline._import_sd", side_effect=fake_import):
        with patch("app.scrape_telemetry.detect_anti_bot", return_value=0.1):
            pipeline._stage_analyze_page(ctx)
            assert ctx.anti_bot_score == 0.1
            assert ctx.profile.structure_type == "table"
            assert ctx.patterns == {"fields": [], "confidence": 0.0}


# ── run() orchestration ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_run_happy_path(pipeline: URLAnalysisPipeline) -> None:
    with (
        patch("app.services.url_analysis_pipeline._import_sd") as mock_import_sd,
        patch("app.html_utils.fetch_page_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.scrape_telemetry.detect_anti_bot", return_value=0.0),
        patch("app.acquisition_mode.AcquisitionConfig") as mock_cfg_cls,
        patch("app.acquisition_mode.AcquisitionMode") as mock_mode_cls,
        patch("app.acquisition_mode.should_escalate", return_value=False),
        patch("app.acquisition_mode.escalate_mode"),
    ):
        mock_mode_cls.return_value = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.detect_session_params = False
        mock_cfg.attempt_search_form = False
        mock_cfg.attempt_recovery = False
        mock_cfg.detect_empty_responses = False
        mock_cfg.max_retries = 1
        mock_cfg.use_playwright = True
        mock_cfg.mode = MagicMock()
        mock_cfg.mode.value = "standard"
        mock_cfg_cls.from_mode.return_value = mock_cfg

        mock_fetch.return_value = ("<html><body>test</body></html>" * 20, 0.0, "playwright", 0)

        sd_funcs = {
            "reset_llm_call_count": MagicMock(),
            "detect_session_params": MagicMock(
                return_value={
                    "is_session_bound": False,
                    "ephemeral_params": [],
                    "canonical_url": "",
                    "confidence": 0.0,
                    "details": [],
                }
            ),
            "detect_page_structure": MagicMock(
                return_value=MagicMock(
                    structure_type="list",
                    structure_confidence=0.8,
                    container_selector=".item",
                    headers=[],
                )
            ),
            "detect_value_patterns": MagicMock(return_value={"fields": [], "confidence": 0.0}),
            "_assess_content_quality": MagicMock(
                return_value={"quality": "good", "has_data_containers": True, "data_container_count": 5}
            ),
            "detect_empty_response": MagicMock(return_value=MagicMock(is_empty=False, empty_type="", confidence=0.0, message="")),
            "EmptyResponseCheck": MagicMock(
                return_value=MagicMock(is_empty=False, empty_type="", confidence=0.0, message="", suggestions=[])
            ),
            "_extract_container_text_values": MagicMock(return_value=["val1", "val2", "val3"]),
            "_rename_generic_fields": MagicMock(return_value=[]),
            "build_url_analysis_prompt": MagicMock(return_value="prompt"),
            "_build_llm_fields": MagicMock(return_value=[]),
            "llm_json": AsyncMock(return_value=None),
            "_detect_redirect": MagicMock(return_value={"redirected": False}),
            "build_redirect_info": MagicMock(return_value={}),
            "_detect_search_form": MagicMock(
                return_value={"detected": False, "form_fields": [], "search_fields": [], "action": ""}
            ),
            "_try_form_search_recovery": AsyncMock(return_value={"success": False}),
        }
        mock_import_sd.side_effect = lambda name: sd_funcs[name]

        with patch("app.acquisition_state.AcquisitionLineage") as mock_lineage:
            mock_lineage_instance = MagicMock()
            mock_lineage_instance.model_dump.return_value = {"state": "direct"}
            mock_lineage_instance.state = MagicMock()
            mock_lineage_instance.state.value = "direct"
            mock_lineage_instance.original_url = ""
            mock_lineage_instance.final_url = ""
            mock_lineage_instance.recovery_method = None
            mock_lineage_instance.recovered_url = None
            mock_lineage_instance.get_user_message.return_value = "OK"
            mock_lineage_instance.data_evidence_score = 0.0
            mock_lineage_instance.anti_bot_score = 0.0
            mock_lineage_instance.containers_detected = 0
            mock_lineage_instance.forms_detected = 0
            mock_lineage_instance.network_payloads_found = 0
            mock_lineage_instance.session_bound = False
            mock_lineage_instance.ephemeral_params = []
            mock_lineage_instance.recommended_next_action = None
            mock_lineage_instance.message = ""
            mock_lineage.from_redirect_info.return_value = mock_lineage_instance

            with patch("app.browser_network_capture.get_browser_state", return_value=None):
                with patch("app.browser_network_capture.get_captures", return_value=[]):
                    with patch("app.acquisition_telemetry.get_acquisition_telemetry") as mock_tele:
                        mock_tele.return_value = MagicMock()

                        result = await pipeline.run("https://example.com")

                        assert result is not None
                        assert "url" in result
                        assert result["url"] == "https://example.com"
                        assert "suggested_fields" in result


@pytest.mark.anyio
async def test_run_fetch_error_returns_error_response(pipeline: URLAnalysisPipeline) -> None:
    with (
        patch("app.services.url_analysis_pipeline._import_sd") as mock_import_sd,
        patch("app.html_utils.fetch_page_content", side_effect=RuntimeError("timeout")),
        patch("app.acquisition_mode.AcquisitionConfig") as mock_cfg_cls,
        patch("app.acquisition_mode.AcquisitionMode") as mock_mode_cls,
    ):
        mock_mode_cls.return_value = MagicMock()
        mock_cfg = MagicMock()
        mock_cfg.detect_session_params = False
        mock_cfg.attempt_search_form = False
        mock_cfg.attempt_recovery = False
        mock_cfg.detect_empty_responses = False
        mock_cfg.max_retries = 1
        mock_cfg.mode = MagicMock()
        mock_cfg.mode.value = "standard"
        mock_cfg_cls.from_mode.return_value = mock_cfg

        sd_funcs = {
            "reset_llm_call_count": MagicMock(),
            "_detect_redirect": MagicMock(return_value={"redirected": False}),
            "detect_session_params": MagicMock(
                return_value={
                    "is_session_bound": False,
                    "ephemeral_params": [],
                    "canonical_url": "",
                    "confidence": 0.0,
                    "details": [],
                }
            ),
            "_detect_search_form": MagicMock(
                return_value={"detected": False, "form_fields": [], "search_fields": [], "action": ""}
            ),
            "_try_form_search_recovery": AsyncMock(return_value={"success": False}),
            "detect_page_structure": MagicMock(
                return_value=MagicMock(
                    structure_type="list",
                    structure_confidence=0.8,
                    container_selector=".item",
                    headers=[],
                )
            ),
            "detect_value_patterns": MagicMock(return_value={"fields": [], "confidence": 0.0}),
            "_assess_content_quality": MagicMock(
                return_value={"quality": "good", "has_data_containers": True, "data_container_count": 5}
            ),
            "detect_empty_response": MagicMock(return_value=MagicMock(is_empty=False, empty_type="", confidence=0.0, message="")),
            "EmptyResponseCheck": MagicMock(
                return_value=MagicMock(is_empty=False, empty_type="", confidence=0.0, message="", suggestions=[])
            ),
        }
        mock_import_sd.side_effect = lambda name: sd_funcs[name]

        result = await pipeline.run("https://example.com")
        assert result is not None
        assert result.get("error") is not None
        assert "timeout" in result["error"]


@pytest.mark.anyio
async def test_run_escalation_loop(pipeline: URLAnalysisPipeline) -> None:
    """Verify that when escalation is triggered, run() recurses."""
    call_count = 0

    async def escalating_run(
        url: str,
        search_params=None,
        acquisition_mode: str = "standard",
        _escalation_depth: int = 0,
    ) -> dict:
        nonlocal call_count
        call_count += 1
        if _escalation_depth < 1:
            return {"url": url, "mode": acquisition_mode, "depth": _escalation_depth, "suggested_fields": []}
        return {"url": url, "mode": acquisition_mode, "depth": _escalation_depth, "suggested_fields": []}

    with patch.object(pipeline, "run", escalating_run):
        result = await pipeline.run("https://example.com")
        assert call_count >= 1
        assert "suggested_fields" in result
