"""Tests for redirect detection and content quality assessment in URL Analyzer."""

from app.selector_discovery import _detect_redirect, _assess_content_quality


class TestDetectRedirect:
    """Tests for _detect_redirect — URL path comparison logic."""

    def test_no_redirect_same_url(self):
        result = _detect_redirect(
            "https://example.com/search/results",
            "https://example.com/search/results",
        )
        assert result["redirected"] is False
        assert result["redirect_type"] == "none"

    def test_no_redirect_trailing_slash(self):
        result = _detect_redirect(
            "https://example.com/search/results",
            "https://example.com/search/results/",
        )
        assert result["redirected"] is False
        assert result["redirect_type"] == "none"

    def test_homepage_redirect(self):
        result = _detect_redirect(
            "https://www.cheapflightsfares.com/search/id/SaCLIvTQmmfXOHXOFqMzQOfK",
            "https://www.cheapflightsfares.com/",
        )
        assert result["redirected"] is True
        # 3+ path segments → homepage → classified as session_expired
        # (the search token/identifier expired, causing redirect to homepage)
        assert result["redirect_type"] == "session_expired"
        assert "expired" in result["message"].lower()

    def test_session_expired_redirect(self):
        result = _detect_redirect(
            "https://example.com/flights/search/abc123def",
            "https://example.com/flights",
        )
        assert result["redirected"] is True
        assert result["redirect_type"] == "session_expired"
        assert "expired" in result["message"].lower()

    def test_path_changed_redirect(self):
        result = _detect_redirect(
            "https://example.com/old-path",
            "https://example.com/new-path",
        )
        assert result["redirected"] is True
        assert result["redirect_type"] == "path_changed"

    def test_cross_domain_not_flagged(self):
        """Cross-domain redirects (different netloc) are not flagged as redirects."""
        result = _detect_redirect(
            "https://example.com/search",
            "https://other.com/results",
        )
        # Different netloc — not a same-site redirect
        assert result["redirected"] is False
        assert result["redirect_type"] == "none"

    def test_preserves_original_and_final_urls(self):
        original = "https://example.com/a/b/c"
        final = "https://example.com/"
        result = _detect_redirect(original, final)
        assert result["original_url"] == original
        assert result["final_url"] == final


class TestAssessContentQuality:
    """Tests for _assess_content_quality — landing page vs data page detection."""

    def test_good_quality_with_many_cards(self):
        html = "<html><body>" + "".join(
            f'<div class="result-card">New York → London £{i}50 - Flight {i} results</div>'
            for i in range(10)
        ) + "</body></html>"

        class MockProfile:
            container_selector = "div.result-card"

        result = _assess_content_quality(html, MockProfile())
        assert result["has_data_containers"] is True
        assert result["quality"] == "good"
        assert result["data_container_count"] >= 3

    def test_landing_page_with_form(self):
        html = """
        <html><body>
            <div class="hero-banner"><h1>Welcome</h1></div>
            <form><input type="text" /><button>Search</button></form>
            <div>Some content</div>
        </body></html>
        """

        class MockProfile:
            container_selector = "body"

        result = _assess_content_quality(html, MockProfile())
        assert result["is_landing_page"] is True
        assert result["quality"] == "landing_page"
        # Message says "a landing or homepage" ("landing" and "page" not contiguous)
        assert "landing" in result["message"].lower() or "homepage" in result["message"].lower()

    def test_low_quality_no_containers(self):
        html = "<html><body><p>Just a paragraph</p><p>Another one</p></body></html>"

        class MockProfile:
            container_selector = "body"

        result = _assess_content_quality(html, MockProfile())
        assert result["quality"] in ("low", "landing_page")
        assert result["has_data_containers"] is False

    def test_none_profile_handled(self):
        html = "<html><body><div class='card'>A</div></body></html>"
        result = _assess_content_quality(html, None)
        assert isinstance(result, dict)
        assert "quality" in result

    def test_profile_container_used(self):
        html = "<html><body>" + "".join(
            f'<div class="flight-box">Flight to New York City - £{i}50 one-way ticket</div>'
            for i in range(5)
        ) + "</body></html>"

        class MockProfile:
            container_selector = "div.flight-box"

        result = _assess_content_quality(html, MockProfile())
        assert result["has_data_containers"] is True
        assert result["data_container_count"] >= 5
