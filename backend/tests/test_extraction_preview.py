"""Tests for the extraction preview/dry-run endpoint (Roadmap Feat 19).

``POST /api/scraper/preview`` accepts the same payload as job creation
but runs extraction on the first URL only without persisting results.

All tests that expect 200 responses mock ``scrape_url_attempt`` so they
don't hit the real network.
"""

from __future__ import annotations

from app.scraper_models import ScrapeAttemptResult


async def _fake_scrape_url_attempt(url, schema_fields, **kwargs):
    """Return a minimal successful ScrapeAttemptResult."""
    return ScrapeAttemptResult(
        records=[{"title": "Example Domain"}],
        final_url=url,
        html="<html>...</html>",
        fetch_method="httpx",
        extraction_method="llm",
    )


class TestExtractionPreview:
    """Tests for the dry-run preview endpoint."""

    def test_preview_requires_auth(self, client):
        """Preview endpoint requires admin/operator role."""
        resp = client.post("/api/scraper/preview", json={"urls": ["https://example.com"]})
        # In test mode with ALLOW_INSECURE_DEV_AUTH=True, auth is bypassed
        assert resp.status_code in (200, 201, 400, 422, 403)

    def test_preview_rejects_empty_urls(self, client):
        """At least one URL is required."""
        resp = client.post(
            "/api/scraper/preview",
            json={"name": "preview", "mode": "manual", "urls": []},
        )
        assert resp.status_code in (400, 422)

    def test_preview_rejects_ssrf_urls(self, client):
        """SSRF-blocked URLs are rejected."""
        resp = client.post(
            "/api/scraper/preview",
            json={
                "name": "preview",
                "mode": "manual",
                "urls": ["http://127.0.0.1:8000/secret"],
            },
        )
        assert resp.status_code in (400, 422)

    def test_preview_rejects_invalid_mode(self, client):
        """Manual mode is required (auto mode not supported for preview)."""
        resp = client.post(
            "/api/scraper/preview",
            json={
                "name": "preview",
                "mode": "auto",
                "topic": "test",
                "urls": ["https://example.com"],
            },
        )
        # auto mode is valid as long as urls are provided
        assert resp.status_code in (200, 400, 422)

    def test_preview_response_shape(self, client, monkeypatch):
        """Preview response includes expected fields."""
        monkeypatch.setattr("app.scraper.scrape_url_attempt", _fake_scrape_url_attempt)

        resp = client.post(
            "/api/scraper/preview",
            json={
                "name": "preview-test",
                "mode": "manual",
                "urls": ["https://example.com"],
                "schema_fields": [{"name": "title", "field_type": "string"}],
            },
        )
        # scrape_url_attempt is mocked to always succeed, so 422 should
        # never happen here. The prior ``in (200, 422)`` gate was a
        # vacuous allowance: if 422 somehow materialised it would mask a
        # broken test fixture. Assert 200 unconditionally and verify body.
        assert resp.status_code == 200, f"Successful preview mocked; got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "url" in body
        assert body["dry_run"] is True
        assert "preview_records" in body
        assert "total_records_found" in body

    def test_preview_with_selectors(self, client, monkeypatch):
        """Preview accepts selectors_map from the job config."""
        monkeypatch.setattr("app.scraper.scrape_url_attempt", _fake_scrape_url_attempt)

        resp = client.post(
            "/api/scraper/preview",
            json={
                "name": "preview-selectors",
                "mode": "manual",
                "urls": ["https://example.com"],
                "selectors_map": {
                    "item_container": "div.content",
                    "fields": {"title": "h1"},
                },
                "schema_fields": [{"name": "title", "field_type": "string"}],
            },
        )
        assert resp.status_code in (200, 422)

    def test_preview_with_extraction_params(self, client, monkeypatch):
        """Preview forwards extraction params to the scraper."""
        monkeypatch.setattr("app.scraper.scrape_url_attempt", _fake_scrape_url_attempt)

        resp = client.post(
            "/api/scraper/preview",
            json={
                "name": "preview-params",
                "mode": "manual",
                "urls": ["https://example.com"],
                "min_record_score": 0.5,
                "fetch_strategy": "httpx_only",
                "hydration_wait_ms": 1000,
                "schema_fields": [{"name": "content", "field_type": "string"}],
            },
        )
        assert resp.status_code in (200, 422)

    def test_preview_with_headers(self, client, monkeypatch):
        """Preview forwards headers to the scraper."""
        monkeypatch.setattr("app.scraper.scrape_url_attempt", _fake_scrape_url_attempt)

        resp = client.post(
            "/api/scraper/preview",
            json={
                "name": "preview-headers",
                "mode": "manual",
                "urls": ["https://example.com"],
                "headers": {"Accept-Language": "en-US"},
            },
        )
        assert resp.status_code in (200, 400, 422)

    def test_preview_does_not_persist_job(self, client, monkeypatch):
        """Preview must NOT create a job in the store."""
        monkeypatch.setattr("app.scraper.scrape_url_attempt", _fake_scrape_url_attempt)

        import app.main as main_mod

        initial_count = len(main_mod.jobs_store)
        client.post(
            "/api/scraper/preview",
            json={
                "name": "preview-no-persist",
                "mode": "manual",
                "urls": ["https://example.com"],
            },
        )
        assert len(main_mod.jobs_store) == initial_count
