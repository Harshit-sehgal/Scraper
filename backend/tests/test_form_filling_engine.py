"""Tests for the Form Filling Engine (Feat 8).

Covers form detection, field mapping, Playwright-level filling, and
HTTP-level submission.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.form_filling_engine import (
    _build_css_selector,
    _extract_label,
    _extract_select_options,
    detect_form_fields,
    fill_form_fields,
    map_form_fields_to_values,
    submit_form,
    submit_form_http,
)

# ─── Sample HTML fixtures ──────────────────────────────────────────────

SIMPLE_SEARCH_FORM_HTML = """
<html>
<body>
<form id="search-form" action="/search" method="POST">
    <label for="origin">Origin</label>
    <input type="text" id="origin" name="origin" placeholder="From" required>

    <label for="destination">Destination</label>
    <input type="text" id="destination" name="destination" placeholder="To" required>

    <label for="date">Date</label>
    <input type="date" id="date" name="departure_date">

    <label for="passengers">Passengers</label>
    <select id="passengers" name="passengers" required>
        <option value="1">1 Adult</option>
        <option value="2" selected>2 Adults</option>
        <option value="3">3 Adults</option>
    </select>

    <button type="submit">Search</button>
</form>
</body>
</html>
"""

LOGIN_FORM_HTML = """
<html>
<body>
<form id="login" action="/auth/login" method="POST">
    <label for="email">Email</label>
    <input type="email" id="email" name="email" placeholder="your@email.com" required>

    <label for="password">Password</label>
    <input type="password" id="password" name="password" required>

    <label>
        <input type="checkbox" name="remember" value="1"> Remember me
    </label>

    <button type="submit">Log In</button>
    <input type="hidden" name="csrf_token" value="abc123">
</form>
</body>
</html>
"""

NO_FORM_HTML = """
<html>
<body>
<h1>Welcome</h1>
<p>No forms here.</p>
</body>
</html>
"""

SPA_FORM_HTML = """
<html>
<body>
<input type="text" id="search-box" name="q" placeholder="Search...">
<button id="search-btn">Go</button>
</body>
</html>
"""

EMPTY_HTML = ""


class TestFormDetection:
    """Unit tests for HTML form detection."""

    def test_detect_simple_search_form(self) -> None:
        forms = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)
        assert len(forms) == 1
        form = forms[0]
        assert form["id"] == "search-form"
        assert form["action"] == "/search"
        assert form["method"] == "POST"
        assert form["field_count"] == 4

    def test_detect_search_form_fields(self) -> None:
        forms = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)
        fields = forms[0]["fields"]
        field_names = [f["name"] for f in fields]
        assert "origin" in field_names
        assert "destination" in field_names
        assert "departure_date" in field_names
        assert "passengers" in field_names

    def test_detect_field_types(self) -> None:
        forms = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)
        fields = {f["name"]: f for f in forms[0]["fields"]}

        assert fields["origin"]["element_type"] == "input"
        assert fields["origin"]["input_type"] == "text"
        assert fields["origin"]["required"] is True
        assert fields["origin"]["placeholder"] == "From"

        assert fields["passengers"]["element_type"] == "select"
        assert len(fields["passengers"]["options"]) == 3

        assert fields["departure_date"]["input_type"] == "date"

    def test_detect_select_options(self) -> None:
        forms = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)
        passengers = next(f for f in forms[0]["fields"] if f["name"] == "passengers")
        options = passengers["options"]
        assert len(options) == 3
        assert options[0]["value"] == "1"
        assert options[0]["text"] == "1 Adult"
        assert options[2]["value"] == "3"

    def test_detect_submit_button(self) -> None:
        forms = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)
        btn = forms[0]["submit_button"]
        assert btn is not None
        assert btn["value"] == "Search"
        assert "submit" in btn["selector"]

    def test_detect_login_form_with_checkbox(self) -> None:
        forms = detect_form_fields(LOGIN_FORM_HTML)
        assert len(forms) == 1
        fields = forms[0]["fields"]
        field_names = [f["name"] for f in fields]
        assert "email" in field_names
        assert "password" in field_names
        assert "remember" in field_names
        # Hidden fields should be skipped
        assert "csrf_token" not in field_names

    def test_login_form_checkbox_type(self) -> None:
        forms = detect_form_fields(LOGIN_FORM_HTML)
        remember = next(f for f in forms[0]["fields"] if f["name"] == "remember")
        assert remember["is_choice"] is True
        assert remember["input_type"] == "checkbox"

    def test_no_form_returns_empty_list(self) -> None:
        forms = detect_form_fields(NO_FORM_HTML)
        assert forms == []

    def test_empty_html_returns_empty_list(self) -> None:
        forms = detect_form_fields(EMPTY_HTML)
        assert forms == []

    def test_detect_standalone_spa_fields(self) -> None:
        forms = detect_form_fields(SPA_FORM_HTML)
        assert len(forms) == 1
        assert forms[0].get("standalone") is True
        assert forms[0]["field_count"] == 1
        assert forms[0]["fields"][0]["name"] == "q"
        assert forms[0]["submit_button"] is not None

    def test_field_labels_extracted(self) -> None:
        forms = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)
        fields = {f["name"]: f for f in forms[0]["fields"]}
        # Labels from label elements
        assert "origin" in fields
        assert fields["origin"]["label"] == "Origin" or fields["origin"]["label"] != ""

    def test_extract_select_options_empty(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<input type='text'>", "html.parser")
        options = _extract_select_options(soup.find("input"))
        assert options == []

    def test_extract_label_from_aria(self) -> None:
        from bs4 import BeautifulSoup

        html = '<input type="text" name="test" aria-label="Test Label">'
        soup = BeautifulSoup(html, "html.parser")
        label = _extract_label(soup, soup.find("input"))
        assert label == "Test Label"


class TestFieldMapping:
    """Tests for fuzzy field name mapping."""

    def test_exact_name_match(self) -> None:
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        mapped = map_form_fields_to_values(form, {"origin": "NYC"})
        assert mapped.get("origin") == "NYC"

    def test_multiple_field_mapping(self) -> None:
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        mapped = map_form_fields_to_values(
            form,
            {
                "origin": "New York",
                "destination": "Los Angeles",
                "departure_date": "2026-07-15",
                "passengers": "2",
            },
        )
        assert mapped.get("origin") == "New York"
        assert mapped.get("destination") == "Los Angeles"
        assert mapped.get("departure_date") == "2026-07-15"
        assert mapped.get("passengers") == "2"

    def test_fuzzy_name_match(self) -> None:
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        # "from" should fuzzy-match to "origin"
        mapped = map_form_fields_to_values(form, {"from": "NYC", "to": "LAX"})
        # "from" maps to "origin", "to" maps to "destination"
        assert mapped.get("origin") == "NYC"
        assert mapped.get("destination") == "LAX"

    def test_empty_values_ignored(self) -> None:
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        mapped = map_form_fields_to_values(form, {"origin": "", "destination": "LAX"})
        assert "origin" not in mapped or mapped.get("origin") != ""
        assert mapped.get("destination") == "LAX"

    def test_unknown_field_ignored(self) -> None:
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        mapped = map_form_fields_to_values(form, {"nonexistent_field": "value"})
        assert "nonexistent_field" not in mapped

    def test_empty_form_returns_empty(self) -> None:
        mapped = map_form_fields_to_values({}, {"test": "value"})
        assert mapped == {}

    def test_empty_values_dict_returns_empty(self) -> None:
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        mapped = map_form_fields_to_values(form, {})
        assert mapped == {}

    def test_placeholder_label_match(self) -> None:
        """Fields with matching placeholders should be found."""
        form = detect_form_fields(SIMPLE_SEARCH_FORM_HTML)[0]
        mapped = map_form_fields_to_values(form, {"from": "NYC"})
        assert mapped.get("origin") == "NYC"


class TestBuildCssSelector:
    """Tests for CSS selector generation."""

    def test_selector_by_id(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<input id="foo" name="bar">', "html.parser")
        sel = _build_css_selector(soup.find("input"), "#myform")
        assert "#foo" in sel

    def test_selector_by_name(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<input name="bar">', "html.parser")
        sel = _build_css_selector(soup.find("input"), "#myform")
        assert 'name="bar"' in sel

    def test_selector_unknown_fallback(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<input>", "html.parser")
        sel = _build_css_selector(soup.find("input"), "#myform")
        assert sel == "#myform input" or "input" in sel


class TestFormFillingBrowser:
    """Tests for Playwright-level form filling (mocked)."""

    @pytest.mark.asyncio
    async def test_fill_form_fields_success(self) -> None:
        """All fields are filled successfully."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = mock_locator

        # Mock element info
        mock_locator.evaluate = AsyncMock(
            side_effect=[
                "input",
                "text",  # first field
                "input",
                "text",  # second field
            ]
        )
        mock_locator.fill = AsyncMock()
        mock_page.locator.return_value = mock_locator

        results = await fill_form_fields(mock_page, "#myform", {"name": "John", "email": "john@test.com"})
        assert len(results) == 2
        assert results[0]["status"] == "ok"
        assert results[1]["status"] == "ok"
        assert mock_locator.fill.call_count == 2

    @pytest.mark.asyncio
    async def test_fill_form_field_not_found(self) -> None:
        """Missing fields are reported as skipped."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0  # field not found
        mock_page.locator.return_value = mock_locator

        results = await fill_form_fields(mock_page, "#myform", {"unknown": "value"})
        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert "not found" in results[0].get("error", "")

    @pytest.mark.asyncio
    async def test_fill_raises_on_none_page(self) -> None:
        """Calling with None page raises RuntimeError."""
        with pytest.raises(RuntimeError, match="requires a valid Playwright page"):
            await fill_form_fields(None, "#form", {"test": "value"})

    @pytest.mark.asyncio
    async def test_fill_select_option(self) -> None:
        """Select elements use select_option."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = mock_locator
        mock_locator.evaluate = AsyncMock(return_value="select")
        mock_locator.select_option = AsyncMock()
        mock_page.locator.return_value = mock_locator

        results = await fill_form_fields(mock_page, "#form", {"country": "US"})
        assert results[0]["status"] == "ok"
        mock_locator.select_option.assert_awaited_once_with("US", timeout=30_000)

    @pytest.mark.asyncio
    async def test_fill_checkbox_true(self) -> None:
        """Checkboxes are checked when value is truthy."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = mock_locator
        mock_locator.evaluate = AsyncMock(return_value="input", side_effect=["input", "checkbox"])
        mock_locator.is_checked = AsyncMock(return_value=False)
        mock_locator.check = AsyncMock()
        mock_page.locator.return_value = mock_locator

        results = await fill_form_fields(mock_page, "#form", {"agree": "true"})
        assert results[0]["status"] == "ok"
        mock_locator.check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fill_textarea(self) -> None:
        """Textareas use .fill()."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = mock_locator
        mock_locator.evaluate = AsyncMock(return_value="textarea")
        mock_locator.fill = AsyncMock()
        mock_page.locator.return_value = mock_locator

        results = await fill_form_fields(mock_page, "#form", {"bio": "Hello world"})
        assert results[0]["status"] == "ok"
        mock_locator.fill.assert_awaited_once_with("Hello world", timeout=30_000)

    @pytest.mark.asyncio
    async def test_empty_field_values_skipped(self) -> None:
        """Empty field names are skipped."""
        mock_page = MagicMock()
        results = await fill_form_fields(mock_page, "#form", {"": "value"})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_form_submit_success(self) -> None:
        """Form submission succeeds."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_locator.first = mock_locator
        mock_page.locator.return_value = mock_locator
        mock_page.url = "https://example.com/results"

        result = await submit_form(mock_page, "#form")
        assert result["success"] is True
        assert result["final_url"] == "https://example.com/results"

    @pytest.mark.asyncio
    async def test_submit_no_button_presses_enter(self) -> None:
        """When no submit button, Enter is pressed on the last field."""
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0  # no submit button
        mock_locator.last = mock_locator
        mock_locator.press = AsyncMock()
        mock_page.locator.return_value = mock_locator
        mock_page.url = "https://example.com"

        result = await submit_form(mock_page, "#form")
        mock_locator.press.assert_awaited_once_with("Enter")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_submit_raises_on_none_page(self) -> None:
        """Calling submit_form with None page raises RuntimeError."""
        with pytest.raises(RuntimeError, match="requires a valid Playwright page"):
            await submit_form(None, "#form")


class TestHttpFormSubmission:
    """Tests for HTTP-level form submission (mocked)."""

    @pytest.mark.asyncio
    async def test_http_submit_success(self) -> None:
        """HTTP form submission returns success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Success</body></html>"
        mock_response.url = "https://example.com/search"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response)

        form = {
            "action": "/search",
            "method": "POST",
            "fields": [{"name": "q", "element_type": "input", "input_type": "text"}],
        }

        with patch("app.form_filling_engine.get_safe_async_client", return_value=mock_client):
            result = await submit_form_http(form, "https://example.com/page", {"q": "test"})

        assert result["success"] is True
        assert result["status_code"] == 200
        assert "Success" in result["html"]


class TestDetectStandaloneFields:
    """Tests for standalone field detection (SPA mode)."""

    def test_detect_standalone_fields(self) -> None:
        forms = detect_form_fields(SPA_FORM_HTML)
        assert len(forms) == 1
        form = forms[0]
        assert form.get("standalone") is True
        assert len(form["fields"]) == 1
        assert form["fields"][0]["name"] == "q"
        assert form["fields"][0]["input_type"] == "text"

    def test_standalone_submit_button(self) -> None:
        forms = detect_form_fields(SPA_FORM_HTML)
        btn = forms[0]["submit_button"]
        assert btn is not None
        assert btn["value"] == "Go"
