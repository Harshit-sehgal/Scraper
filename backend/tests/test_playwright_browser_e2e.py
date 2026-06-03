"""True browser E2E test for session-bound pages using Playwright.

Verifies:
- Playwright loads /search/id/<opaque-token> page
- Browser cookies are set via Set-Cookie header
- localStorage and sessionStorage are written by the page
- Network JSON responses are captured
- Structured records are extracted from rendered DOM
- Raw browser secrets are NOT persisted in extraction output
- Session-bound URL detection flags the URL correctly
"""

import http.server
import json
import threading
import urllib.parse

import pytest
from app.models import FieldType, SchemaField

pytestmark = pytest.mark.browser

# Skip if Playwright is not installed
pytest.importorskip("playwright")


SEARCH_HTML = """<!DOCTYPE html>
<html><head><title>Flight Search Results</title></head><body>
<div class="results">
  <div class="card">
    <span class="airline">Test Airways</span>
    <span class="price">$299</span>
    <span class="date">Jun 15, 2026</span>
  </div>
  <div class="card">
    <span class="airline">Demo Airlines</span>
    <span class="price">$450</span>
    <span class="date">Jun 20, 2026</span>
  </div>
</div>
<script>
  localStorage.setItem('search_session', 'browser_tok_abc123');
  sessionStorage.setItem('last_query', 'flights to PAR');
  document.cookie = 'browser_sid=xyz789; path=/';
</script>
</body></html>"""

PIPELINE_HTML = """<!DOCTYPE html>
<html><head><title>Pipeline Search Results</title></head><body>
<div id="results">Loading...</div>
<script>
  fetch('/api/pipeline_results')
    .then(r => r.json())
    .then(data => {
       console.log(data);
    });
</script>
</body></html>"""

API_JSON = json.dumps(
    {
        "results": [
            {"carrier": "Test Airways", "fare": 299, "currency": "USD"},
            {"carrier": "Demo Airlines", "fare": 450, "currency": "USD"},
        ]
    }
)

PIPELINE_JSON = json.dumps(
    {
        "results": [
            {"carrier": "Pipeline Airways", "fare": 999},
            {"carrier": "Route Jet", "fare": 1200},
        ]
    }
)


class _BrowserTestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/search/id/browser_test_token_abc":
            self.send_response(200)
            self.send_header("Set-Cookie", "server_sid=deadbeef; Path=/; HttpOnly")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(SEARCH_HTML.encode())
        elif parsed.path == "/search/id/pipeline_test_token_xyz":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PIPELINE_HTML.encode())
        elif parsed.path == "/api/results":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(API_JSON.encode())
        elif parsed.path == "/api/pipeline_results":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(PIPELINE_JSON.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def browser_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _BrowserTestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_playwright_loads_session_page(browser_server) -> None:
    """Playwright loads the session-bound search page successfully."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        url = f"{browser_server}/search/id/browser_test_token_abc"
        await page.goto(url, wait_until="domcontentloaded")
        content = await page.content()
        assert "Test Airways" in content
        assert "$299" in content
        await browser.close()


@pytest.mark.asyncio
async def test_playwright_captures_cookies(browser_server) -> None:
    """Playwright captures cookies set by the server."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        cookies = await page.context.cookies()
        cookie_names = {c["name"] for c in cookies}
        assert "server_sid" in cookie_names, f"Cookie not set. Got: {cookie_names}"
        await browser.close()


@pytest.mark.asyncio
async def test_playwright_reads_local_storage(browser_server) -> None:
    """Playwright verifies localStorage is written by the page JS."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        val = await page.evaluate("() => localStorage.getItem('search_session')")
        assert val == "browser_tok_abc123", f"localStorage mismatch: {val}"
        await browser.close()


@pytest.mark.asyncio
async def test_playwright_reads_session_storage(browser_server) -> None:
    """Playwright verifies sessionStorage is written by the page JS."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        val = await page.evaluate("() => sessionStorage.getItem('last_query')")
        assert val == "flights to PAR", f"sessionStorage mismatch: {val}"
        await browser.close()


@pytest.mark.asyncio
async def test_playwright_captures_network_response(browser_server) -> None:
    """Playwright captures the /api/results network JSON response."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        captured = []

        async def handle_response(response):
            if "/api/results" in response.url:
                try:
                    body = await response.text()
                    captured.append(body)
                except Exception:
                    pass

        page.on("response", handle_response)
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        await page.goto(f"{browser_server}/api/results", wait_until="domcontentloaded")
        import asyncio as _asyncio

        await _asyncio.sleep(0.5)
        await browser.close()

    assert len(captured) > 0, "No network responses captured"
    # Find the JSON response (not the HTML search page)
    json_body = None
    for body in captured:
        try:
            data = json.loads(body)
            if "results" in data:
                json_body = body
                break
        except Exception:
            pass
    assert json_body is not None, "No JSON API response captured"
    payload = json.loads(json_body)
    assert payload["results"][0]["carrier"] == "Test Airways"


@pytest.mark.asyncio
async def test_playwright_extraction_from_rendered_dom(browser_server) -> None:
    """Extraction works on Playwright-rendered HTML."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        html = await page.content()
        await browser.close()

    from app.selector_engine import apply_selectors

    schema = [
        SchemaField(name="airline", field_type=FieldType.STRING),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]
    selectors = {
        "item_container": "div.card",
        "fields": {"airline": ".airline", "price": ".price"},
    }
    result = apply_selectors(html, selectors, schema)
    records = result if isinstance(result, list) else result[0]
    assert len(records) == 2
    airlines = {r.get("airline") for r in records}
    assert airlines == {"Test Airways", "Demo Airlines"}


@pytest.mark.asyncio
async def test_playwright_secrets_not_in_extraction(browser_server) -> None:
    """Browser storage values do NOT leak into extraction output."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        html = await page.content()
        await browser.close()

    from app.selector_engine import apply_selectors

    schema = [SchemaField(name="airline", field_type=FieldType.STRING)]
    selectors = {"item_container": "div.card", "fields": {"airline": ".airline"}}
    result = apply_selectors(html, selectors, schema)
    records = result if isinstance(result, list) else result[0]
    for r in records:
        for key in r:
            assert "localStorage" not in key
            assert "sessionStorage" not in key
            assert "cookie" not in key.lower()
            assert "browser_tok" not in str(r.get(key, ""))


@pytest.mark.asyncio
async def test_playwright_url_detected_as_session_bound() -> None:
    """Long opaque token in /search/id/ path is detected as session-bound."""
    from app.session_url_detector import detect_session_params

    result = detect_session_params("https://example.com/search/id/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
    assert result.get("is_session_bound") is True, f"Expected session-bound, got: {result}"


@pytest.mark.asyncio
async def test_playwright_network_capture_feeds_extractor(browser_server) -> None:
    """E2E proving actual network capture feeds the extractor."""
    from app.network_payload_extractor import extract_from_network_payloads
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        captured_payloads = []

        async def handle_response(response):
            try:
                ct = "".join(v for k, v in response.headers.items() if k.lower() == "content-type").lower()
                if "application/json" in ct or "results" in response.url.lower():
                    text = await response.text()
                    captured_payloads.append(text)
            except Exception:
                pass

        page.on("response", handle_response)

        # Navigate to page and fetch the API results endpoint
        await page.goto(
            f"{browser_server}/search/id/browser_test_token_abc",
            wait_until="domcontentloaded",
        )
        await page.goto(f"{browser_server}/api/results", wait_until="domcontentloaded")
        await page.wait_for_timeout(500)
        await browser.close()

    # Now verify that the captured response feeds successfully into the network payload extractor
    schema = [
        SchemaField(name="airline", field_type=FieldType.STRING),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]
    assert len(captured_payloads) > 0, "No network JSON response captured"
    result = extract_from_network_payloads(captured_payloads, schema)

    assert result is not None
    assert result.record_count == 2
    assert result.records[0].get("airline") == "Test Airways"
    assert result.records[0].get("price") == 299


@pytest.mark.asyncio
async def test_playwright_pipeline_integration(browser_server, monkeypatch) -> None:
    """True pipeline E2E integration: weak DOM + naturally fetched strong JSON -> chooses network."""
    from app import html_utils, url_safety
    from app.browser_pool import BrowserPool

    monkeypatch.setenv("DATAFORGE_SMOKE_TEST_MODE", "true")
    monkeypatch.setattr(url_safety, "validate_public_http_url", lambda url: None)
    monkeypatch.setattr(html_utils, "_validate_url_safe", lambda url: None)
    pool = BrowserPool()
    monkeypatch.setattr(html_utils, "get_browser_pool", lambda: pool)
    from app.config import settings

    monkeypatch.setattr(settings, "ALLOWED_INTERNAL_HOSTS", "127.0.0.1,localhost")

    from app.scraper import scrape_url_attempt

    schema = [
        SchemaField(name="airline", field_type=FieldType.STRING),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]

    url = f"{browser_server}/search/id/pipeline_test_token_xyz"
    from app.browser_network_capture import clear as clear_network_capture
    from app.crawl_policy import get_crawl_policy

    clear_network_capture(url)
    crawl_policy = get_crawl_policy()
    crawl_policy.reset_domain(url)
    monkeypatch.setattr(crawl_policy, "_default_delay", 0.0)
    monkeypatch.setattr(crawl_policy, "_respect_robots", False)

    try:
        # Run the real scraper attempt (which handles Playwright loading and network capture internally)
        res = await scrape_url_attempt(
            url=url,
            schema_fields=schema,
            min_record_score=0.1,
        )
    finally:
        await pool.close()

    # Assert records were extracted successfully
    assert len(res) == 2

    # Verify exact records and metadata (source/provenance/confidence) are present in the final result
    assert res[0].get("airline") == "Pipeline Airways"
    assert res[0].get("price") == 999

    assert res[0].get("_extraction_source") == "network_payload"
    assert res[0].get("_extraction_confidence") is not None
    prov = res[0].get("_extraction_provenance", {})
    assert "fields" in prov
    assert prov["fields"]["airline"] == "$.results[*].carrier"
    assert prov["fields"]["price"] == "$.results[*].fare"
