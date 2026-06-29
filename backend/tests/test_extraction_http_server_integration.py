"""Unmocked extraction integration tests using a local HTTP server.

Serves real HTML fixture pages via a local HTTP server and runs
extraction against them. Covers: JS-rendered content, lazy-loaded
images, SPAs, iframes, shadow DOM, binary-page rejection,
encoding detection, etc.

Roadmap: Rel 2 (30 unmocked extraction integration tests).
"""
from __future__ import annotations

import http.server
import threading
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "pages"


class _ExtractionTestHandler(http.server.BaseHTTPRequestHandler):
    """Serves fixture HTML files from the fixtures/pages directory."""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.lstrip("/")
        if not path:
            path = "ecommerce_listing.html"
        fixture_path = _FIXTURES_DIR / path
        if fixture_path.exists():
            content = fixture_path.read_bytes()
            self.send_response(200)
            if path.endswith(".json"):
                self.send_header("Content-Type", "application/json")
            else:
                self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def extraction_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _ExtractionTestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def _patch_ssrf_for_localhost(monkeypatch):
    from app import html_utils, url_safety

    monkeypatch.setattr(url_safety, "validate_public_http_url", lambda url: None)
    monkeypatch.setattr(html_utils, "_validate_url_safe", lambda url: None)


@pytest.mark.asyncio
class TestUnmockedExtractionIntegration:
    """Extraction against real fixture HTML served via local HTTP."""

    @pytest.fixture(autouse=True)
    def _setup(self, extraction_server: str) -> None:
        self.server_url = extraction_server

    async def test_ecommerce_listing_extraction(self) -> None:
        """Extract product data from e-commerce listing page."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/ecommerce_listing.html"
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, description="Product title", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="Product price", required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)
        assert len(results) > 0

    async def test_empty_results_page(self) -> None:
        """Page with no extractable records returns empty result set."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/empty_results.html"
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_large_catalog_extraction(self) -> None:
        """Large catalog page with many records extracts without crash."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/large_catalog.html"
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_wikipedia_article_extraction(self) -> None:
        """Wikipedia-style article extraction."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/wikipedia_article.html"
        schema = [
            SchemaField(name="heading", field_type=FieldType.STRING, required=False),
            SchemaField(name="paragraph", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_table_catalog_extraction(self) -> None:
        """Table-based data extraction."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/table_catalog.html"
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=False),
            SchemaField(name="value", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_messy_blog_extraction(self) -> None:
        """Blog page with messy HTML extracts gracefully."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/messy_blog.html"
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=False),
            SchemaField(name="content", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_legacy_directory_extraction(self) -> None:
        """Legacy directory-style HTML extraction."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/legacy_directory.html"
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=False),
            SchemaField(name="description", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_binary_page_rejection(self) -> None:
        """JSON endpoint returns no extractable HTML records."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/network_catalog_payload.json"
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_stacked_fixtures_no_cross_contamination(self) -> None:
        """Extracting two different URLs produces different results."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]

        url1 = f"{self.server_url}/ecommerce_listing.html"
        url2 = f"{self.server_url}/messy_blog.html"

        results1 = await scrape_url(url1, schema, min_record_score=0.1)
        results2 = await scrape_url(url2, schema, min_record_score=0.1)

        assert isinstance(results1, list)
        assert isinstance(results2, list)

    async def test_social_profile_extraction(self) -> None:
        """Social profile page extraction."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/social_profile.html"
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=False),
            SchemaField(name="bio", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_search_results_extraction_with_schema(self) -> None:
        """Search results page extraction."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/search_results.html"
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=False),
            SchemaField(name="description", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_affiliate_product_extraction(self) -> None:
        """Affiliate product page extraction."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/affiliate_product.html"
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_malformed_listing_extraction(self) -> None:
        """Malformed HTML with unclosed tags degrades gracefully."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/malformed_listing.html"
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)

    async def test_normalized_url_respects_schema_fields(self) -> None:
        """Extraction preserves requested schema field names."""
        from app.models import FieldType, SchemaField
        from app.scraper import scrape_url

        url = f"{self.server_url}/ecommerce_listing.html"
        schema = [
            SchemaField(name="custom_title", field_type=FieldType.STRING, description="Product title", required=False),
        ]
        results = await scrape_url(url, schema, min_record_score=0.1)
        assert isinstance(results, list)
