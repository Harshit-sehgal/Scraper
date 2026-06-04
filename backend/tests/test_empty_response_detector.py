"""Tests for the empty response detector."""

from app.empty_response_detector import detect_empty_response


class TestDetectEmptyResponse:
    """Tests for detect_empty_response()."""

    def test_blank_page(self) -> None:
        result = detect_empty_response("")
        assert result.is_empty is True
        assert result.empty_type == "blank"
        assert result.confidence == 1.0

    def test_near_blank_page(self) -> None:
        result = detect_empty_response("<html><body>   </body></html>")
        assert result.is_empty is True
        assert result.empty_type == "blank"

    def test_cookie_wall(self) -> None:
        html = """
        <html><body>
        <div class="cookie-banner">
            <p>We use cookies on our site. Accept all cookies to continue.</p>
            <button>Accept All Cookies</button>
        </div>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is True
        assert result.empty_type == "cookie_wall"
        assert result.suggestions is not None
        assert len(result.suggestions) > 0

    def test_login_wall(self) -> None:
        html = """
        <html><body>
        <div class="login-prompt">
            <h2>Sign in to continue</h2>
            <p>Please sign in to view this content.</p>
        </div>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is True
        assert result.empty_type == "login_wall"

    def test_captcha_page(self) -> None:
        html = """
        <html><body>
        <div class="challenge">
            <p>Verify you are human by completing the CAPTCHA below.</p>
            <div class="g-recaptcha"></div>
        </div>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is True
        assert result.empty_type == "captcha"

    def test_js_shell(self) -> None:
        html = """
        <html><body>
        <noscript>Please enable JavaScript to use this site.</noscript>
        <div id="app"></div>
        <script>document.getElementById('app').innerHTML = 'Loading...';</script>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is True
        assert result.empty_type == "js_shell"

    def test_data_rich_page_not_empty(self) -> None:
        html = """
        <html><body>
        <div class="result">
            <span class="price">$450</span>
            <span class="date">2026-06-15</span>
            <span class="price">$520</span>
            <span class="date">2026-06-16</span>
            <span class="price">$380</span>
            <span class="date">2026-06-17</span>
            <span class="price">$410</span>
            <span class="date">2026-06-18</span>
            <span class="price">$490</span>
            <span class="date">2026-06-19</span>
        </div>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is False
        assert result.data_signals >= 5

    def test_minimal_content_page(self) -> None:
        html = "<html><body><p>Hello world this is a very short page with minimal content that barely qualifies</p></body></html>"
        result = detect_empty_response(html)
        assert result.is_empty is True
        assert result.empty_type == "minimal"

    def test_moderate_content_with_data(self) -> None:
        html = """
        <html><body>
        <div class="info">
            <p>Flight from New York to London on 2026-06-15 costs $450.</p>
        </div>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is False

    def test_meta_redirect(self) -> None:
        html = """
        <html><head>
        <meta http-equiv="refresh" content="0;url=https://example.com/new-page" />
        </head><body>
        <p>Redirecting to the new page...</p>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.is_empty is True
        assert result.empty_type == "redirect_meta"

    def test_suggestions_for_cookie_wall(self) -> None:
        html = """
        <html><body>
        <div>We use cookies. Accept all cookies to continue.</div>
        </body></html>
        """
        result = detect_empty_response(html)
        assert result.suggestions is not None
        assert len(result.suggestions) > 0
        assert "cookie" in result.suggestions[0].lower()
