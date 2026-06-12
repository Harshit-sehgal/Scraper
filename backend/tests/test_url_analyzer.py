from app.url_analyzer import (
    ScrapingMode,
    UrlClassification,
    _detect_api_endpoint,
    _detect_file_download,
    _detect_login_path,
    _detect_pagination_signals,
    _detect_session_signals,
    _has_infinite_scroll_keywords,
    _recommend_mode,
    analyze_url,
    redact_sensitive_url,
    suggested_start_urls,
)

# ─── Core heuristic tests ──────────────────────────────────────────────


class TestDetectSessionSignals:
    """Tests for _detect_session_signals heuristic."""

    def test_detects_sessionid_param(self):
        url = "https://example.com/page?sessionid=abc123"
        result = _detect_session_signals(url)
        assert result["has_session_param"] is True
        assert "sessionid" in result["matched_session_params"]

    def test_detects_token_param(self):
        url = "https://example.com/page?token=xyz789"
        result = _detect_session_signals(url)
        assert result["has_session_param"] is True
        assert "token" in result["matched_session_params"]

    def test_no_session_params(self):
        url = "https://example.com/page?page=1&limit=10"
        result = _detect_session_signals(url)
        assert result["has_session_param"] is False
        assert result["matched_session_params"] == set()

    def test_generic_id_is_not_session_bound(self):
        url = "https://example.com/products?id=123"
        result = _detect_session_signals(url)
        assert result["has_session_param"] is False
        assert result["matched_session_params"] == set()

    def test_multiple_session_params(self):
        url = "https://example.com/page?sessionid=abc&token=def"
        result = _detect_session_signals(url)
        assert result["has_session_param"] is True
        assert result["matched_session_params"] == {"sessionid", "token"}


class TestDetectPaginationSignals:
    """Tests for _detect_pagination_signals heuristic."""

    def test_detects_page_param(self):
        url = "https://example.com/page?page=2"
        result = _detect_pagination_signals(url)
        assert result["has_pagination_param"] is True
        assert "page" in result["matched_pagination_params"]

    def test_detects_offset_param(self):
        url = "https://example.com/items?offset=20&limit=10"
        result = _detect_pagination_signals(url)
        assert result["has_pagination_param"] is True
        assert "offset" in result["matched_pagination_params"]
        assert "limit" in result["matched_pagination_params"]

    def test_path_suggests_pagination(self):
        url = "https://example.com/search/results"
        result = _detect_pagination_signals(url)
        assert result["path_suggests_pagination"] is True

    def test_no_pagination_signals(self):
        url = "https://example.com/about"
        result = _detect_pagination_signals(url)
        assert result["has_pagination_param"] is False
        assert result["path_suggests_pagination"] is False


class TestDetectLoginPath:
    """Tests for _detect_login_path heuristic."""

    def test_detects_login(self):
        assert _detect_login_path("https://example.com/login") is True

    def test_detects_signin(self):
        assert _detect_login_path("https://example.com/signin") is True

    def test_detects_auth(self):
        assert _detect_login_path("https://example.com/auth/oauth") is True

    def test_non_login_path(self):
        assert _detect_login_path("https://example.com/products") is False

    def test_login_as_subpath(self):
        assert _detect_login_path("https://example.com/app/login/") is True


class TestDetectFileDownload:
    """Tests for _detect_file_download heuristic."""

    def test_detects_pdf(self):
        assert _detect_file_download("https://example.com/report.pdf") is True

    def test_detects_csv(self):
        assert _detect_file_download("https://example.com/data.csv") is True

    def test_detects_zip(self):
        assert _detect_file_download("https://example.com/archive.zip") is True

    def test_non_download(self):
        assert _detect_file_download("https://example.com/page.html") is False

    def test_image_extension(self):
        assert _detect_file_download("https://example.com/image.jpg") is True


class TestDetectApiEndpoint:
    """Tests for _detect_api_endpoint heuristic."""

    def test_detects_api_v1(self):
        assert _detect_api_endpoint("https://example.com/api/v1/users") is True

    def test_detects_graphql(self):
        assert _detect_api_endpoint("https://example.com/graphql") is True

    def test_detects_rest(self):
        assert _detect_api_endpoint("https://example.com/rest/") is True

    def test_non_api(self):
        assert _detect_api_endpoint("https://example.com/products") is False

    def test_data_prefix(self):
        assert _detect_api_endpoint("https://example.com/data/items") is True


class TestHasInfiniteScrollKeywords:
    """Tests for _has_infinite_scroll_keywords heuristic."""

    def test_detects_infinite_in_url(self):
        assert _has_infinite_scroll_keywords("https://example.com/infinite-scroll") is True

    def test_detects_lazy_in_query(self):
        assert _has_infinite_scroll_keywords("https://example.com/feed?lazy=true") is True

    def test_detects_loadmore(self):
        assert _has_infinite_scroll_keywords("https://example.com?loadmore=1") is True

    def test_no_infinite_scroll(self):
        assert _has_infinite_scroll_keywords("https://example.com/page?page=1") is False

    def test_detects_timeline(self):
        assert _has_infinite_scroll_keywords("https://example.com/timeline") is True


class TestRecommendMode:
    """Tests for _recommend_mode logic."""

    def test_download_recommends_not_recommended(self):
        mode, steps = _recommend_mode(
            UrlClassification.FILE_DOWNLOAD_PAGE,
            {},
            {},
            False,
            True,
            False,
        )
        assert mode == ScrapingMode.MANUAL_REVIEW_REQUIRED

    def test_login_recommends_auth_profile(self):
        mode, steps = _recommend_mode(
            UrlClassification.LOGIN_REQUIRED_PAGE,
            {},
            {},
            True,
            False,
            False,
        )
        assert mode == ScrapingMode.AUTH_PROFILE

    def test_session_bound_recommends_workflow_replay(self):
        mode, steps = _recommend_mode(
            UrlClassification.SESSION_BOUND_URL,
            {"has_session_param": True},
            {},
            False,
            False,
            False,
        )
        assert mode == ScrapingMode.WORKFLOW_REPLAY

    def test_normal_page_recommends_direct_scrape(self):
        mode, steps = _recommend_mode(
            UrlClassification.NORMAL_STATIC_PAGE,
            {},
            {},
            False,
            False,
            False,
        )
        assert mode == ScrapingMode.DIRECT_SCRAPE

    def test_api_recommends_direct_scrape(self):
        mode, steps = _recommend_mode(
            UrlClassification.NETWORK_API_BACKED_PAGE,
            {},
            {},
            False,
            False,
            True,
        )
        assert mode == ScrapingMode.DIRECT_SCRAPE


# ─── Integration / End-to-end tests ────────────────────────────────────


class TestAnalyzeUrl:
    """End-to-end tests for the public analyze_url API."""

    def test_invalid_url(self):
        result = analyze_url("not-a-url")
        assert result.classification == UrlClassification.UNKNOWN
        assert result.risk == "high"
        assert result.recommended_mode == ScrapingMode.NOT_RECOMMENDED

    def test_normal_static_page(self):
        result = analyze_url("https://example.com/about")
        assert result.classification == UrlClassification.NORMAL_STATIC_PAGE
        assert result.risk == "low"
        assert result.recommended_mode == ScrapingMode.DIRECT_SCRAPE

    def test_pagination_page(self):
        result = analyze_url("https://example.com/items?page=2")
        assert result.classification == UrlClassification.PAGINATION_PAGE
        assert result.risk == "low"

    def test_session_bound(self):
        result = analyze_url("https://example.com/page?token=abc123")
        assert result.classification == UrlClassification.SESSION_BOUND_URL
        assert result.risk == "high"
        assert result.recommended_mode == ScrapingMode.WORKFLOW_REPLAY

    def test_login_page(self):
        result = analyze_url("https://example.com/login")
        assert result.classification == UrlClassification.LOGIN_REQUIRED_PAGE
        assert result.risk == "medium"
        assert result.recommended_mode == ScrapingMode.AUTH_PROFILE

    def test_api_endpoint(self):
        result = analyze_url("https://api.example.com/v1/users")
        assert result.classification == UrlClassification.NETWORK_API_BACKED_PAGE
        assert result.risk == "low"

    def test_file_download(self):
        result = analyze_url("https://example.com/report.pdf")
        assert result.classification == UrlClassification.FILE_DOWNLOAD_PAGE
        assert result.recommended_mode == ScrapingMode.MANUAL_REVIEW_REQUIRED

    def test_infinite_scroll(self):
        result = analyze_url("https://example.com/feed?scroll=infinite")
        assert result.classification == UrlClassification.INFINITE_SCROLL_PAGE

    def test_result_has_signals(self):
        result = analyze_url("https://example.com/page?page=1&token=abc")
        assert "session" in result.signals
        assert "pagination" in result.signals

    def test_to_dict_serializes_correctly(self):
        result = analyze_url("https://example.com/about")
        d = result.to_dict()
        assert d["classification"] == "normal_static_page"
        assert "risk" in d
        assert "recommended_mode" in d
        assert "signals" in d


class TestPrompt8GuidedUrlIntelligence:
    """Prompt 8 guided scrape-entry contract tests."""

    def test_normal_url_recommends_direct_scrape(self):
        result = analyze_url("https://example.com/about").to_guided_dict()
        assert result["safe_to_fetch"] is True
        assert result["recommended_mode"] == "direct_scrape"
        assert result["risk_level"] == "low"
        assert result["classifications"][0]["type"] == "normal_static_page"

    def test_session_id_url_recommends_workflow_replay_and_redacts(self):
        url = "https://example.com/search/results?sessionId=abc123xyz789&q=laptops"
        result = analyze_url(url).to_guided_dict()
        assert result["recommended_mode"] == "workflow_replay_recommended"
        assert result["risk_level"] == "high"
        assert result["classifications"][0]["type"] == "session_bound_url"
        assert result["redactions_applied"] is True
        assert "abc123xyz789" not in str(result)
        assert "abc1...x789" in str(result)
        assert result["suggested_start_urls"][0]["url"] == "https://example.com/search"
        assert result["suggested_start_urls"][1]["url"] == "https://example.com/"

    def test_supported_temporary_params_are_session_bound(self):
        for param in ("sid", "token", "searchId", "resultId"):
            result = analyze_url(f"https://example.com/results?{param}=abc123xyz789").to_guided_dict()
            assert result["recommended_mode"] == "workflow_replay_recommended"
            assert result["classifications"][0]["type"] == "session_bound_url"

    def test_login_url_recommends_auth_profile(self):
        result = analyze_url("https://example.com/login").to_guided_dict()
        assert result["recommended_mode"] == "auth_profile_recommended"
        assert result["classifications"][0]["type"] == "login_required_page"

    def test_redact_sensitive_url_preserves_non_sensitive_params(self):
        redacted, applied = redact_sensitive_url(
            "https://example.com/path?token=abc123xyz789&id=42&q=laptops",
        )
        assert applied is True
        assert "abc123xyz789" not in redacted
        assert "abc1...x789" in redacted
        assert "id=42" in redacted
        assert "q=laptops" in redacted

    def test_start_url_suggestions_use_parent_and_root(self):
        suggestions = suggested_start_urls("https://example.com/search/results?sessionId=abc123")
        assert [item["url"] for item in suggestions] == [
            "https://example.com/search",
            "https://example.com/",
        ]


class TestPrompt8UrlIntelligenceRoutes:
    """Prompt 8 API route contract tests."""

    def test_no_fetch_api_returns_guided_response(self, client):
        response = client.post(
            "/api/url/analyze",
            json={"url": "https://example.com/about", "fetch_preview": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["recommended_mode"] == "direct_scrape"
        assert data["classifications"][0]["type"] == "normal_static_page"
        assert "suggested_fields" not in data

    def test_unsafe_internal_url_is_blocked_without_fetch(self, client):
        response = client.post(
            "/api/url/analyze",
            json={"url": "http://127.0.0.1:8000/admin", "fetch_preview": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["safe_to_fetch"] is False
        assert data["risk_level"] == "blocked"
        assert data["recommended_mode"] == "blocked_or_unsafe"
        assert data["classifications"][0]["type"] == "unsafe_url"

    def test_workflow_draft_from_session_url_uses_redacted_original(self, client):
        response = client.post(
            "/api/workflow-drafts/from-url-analysis",
            json={"original_url": "https://example.com/search/results?sessionId=abc123xyz789"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["initial_mode"] == "workflow_replay"
        assert data["selected_start_url"] == "https://example.com/search"
        assert data["recommended_start_urls"][0]["url"] == "https://example.com/search"
        assert "abc123xyz789" not in str(data)
