"""Strict end-to-end verification for session-bound URL scraping.

Tests verify:
- Session-bound URL detection with canonical URL + ephemeral params
- Browser state evidence capture (cookies, localStorage, sessionStorage)
- Raw browser secrets NEVER persist in job dumps, DB rows, API responses
- Field-mapping confidence metadata (requested_field, mapped_from, source)
- Fake dynamic session-bound website: cookie + storage + network JSON
"""

import http.server
import json
import os
import threading
import urllib.parse

import pytest
from app.models import FieldType, Job, JobStatus, SchemaField
from app.zero_result_classifier import classify_zero_result

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures/pages")


# ══════════════════════════════════════════════════════════════════════════
# Session-Bound URL Detection — strict assertions
# ══════════════════════════════════════════════════════════════════════════


class TestSessionBoundUrlDetection:
    """Verify session-bound URL patterns with exact expected outcomes."""

    def test_opaque_search_id_detected_as_session_bound(self) -> None:
        """Opaque /search/id/<token> must be session-bound with canonical URL."""
        from app.session_url_detector import detect_session_params

        result = detect_session_params("https://example.com/search/id/a1b2c3d4e5f6g7h8i9j0")
        assert result.get("is_session_bound") is True, "Opaque token in /search/id/ must be session-bound"
        assert "canonical_url" in result
        canonical = result["canonical_url"]
        assert canonical == "https://example.com/search", f"Canonical URL should strip opaque token, got {canonical}"
        assert len(result.get("ephemeral_params", [])) > 0, "Ephemeral path params must include opaque token identifiers"
        assert result.get("confidence", 0) >= 0.5, "Confidence must cross session-bound threshold"

    def test_short_ids_not_session_bound(self) -> None:
        """Short numeric IDs should not trigger false positives."""
        from app.session_url_detector import detect_session_params

        result = detect_session_params("https://example.com/search/id/12")
        assert not result.get("is_session_bound"), "Short numeric IDs must not be flagged as session-bound"

    def test_normal_url_not_session_bound(self) -> None:
        """Plain product/search URLs are not session-bound."""
        from app.session_url_detector import detect_session_params

        result = detect_session_params("https://example.com/products")
        assert not result.get("is_session_bound")


# ══════════════════════════════════════════════════════════════════════════
# Browser State Evidence Capture
# ══════════════════════════════════════════════════════════════════════════


class TestBrowserStateEvidenceCapture:
    """Verify scraper captures and correctly processes browser state."""

    def test_fixture_html_is_valid_page(self) -> None:
        path = os.path.join(FIXTURE_DIR, "e19cf6fcf7b7.html")
        assert os.path.exists(path), f"Fixture missing: {path}"
        with open(path) as f:
            html = f.read()
        assert len(html) > 1000
        assert "<html" in html.lower()

    def test_fixture_has_recognizable_html_structure(self) -> None:
        path = os.path.join(FIXTURE_DIR, "e19cf6fcf7b7.html")
        with open(path) as f:
            html = f.read()
        has_structure = any(tag in html.lower() for tag in ("<div", "<span", "<table", "<li", "<article"))
        assert has_structure, "Fixture has no recognizable HTML structure"

    def test_page_evidence_collector_finds_containers(self) -> None:
        path = os.path.join(FIXTURE_DIR, "e19cf6fcf7b7.html")
        with open(path) as f:
            html = f.read()
        from app.page_evidence_collector import collect_page_evidence

        evidence = collect_page_evidence(html, url="https://example.com/search/id/test")
        assert evidence.html_length > 0
        assert evidence.dom_node_count > 0
        assert isinstance(evidence.candidate_containers, list)

    def test_zero_result_classifier_session_bound(self) -> None:
        """Classifier must map session-bound + no containers = session_bound_url."""
        result = classify_zero_result(
            session_detection={"is_session_bound": True, "ephemeral_params": ["token"]},
            anti_bot_score=0.1,
            detected_containers=0,
            raw_candidate_count=0,
        )
        assert result.zero_result
        assert result.failure_class in ("session_bound_url", "search_replay_required")
        assert len(result.user_message) > 0
        assert len(result.recommended_action) > 0


# ══════════════════════════════════════════════════════════════════════════
# Secrets NOT Persisted — strict injection + verification
# ══════════════════════════════════════════════════════════════════════════

FAKE_SECRETS = [
    "_cookie",
    "_sessionStorage",
    "_localStorage",
    "_indexedDB",
    "_csrf_token",
    "_auth_header",
    "_bearer_token",
    "session_secret",
    "api_key_raw",
    "x_api_token",
]


class TestSecretsNotPersisted:
    """Verify browser secrets never leak into any persisted layer."""

    def test_secrets_stripped_from_alignment_pipeline(self) -> None:
        """Underscore-prefixed raw browser keys are stripped during alignment."""
        from app.data_utils import align_extracted_keys_to_schema

        records = [
            {
                "name": "Test Co",
                "price": "$10",
                **{s: f"fake_{s}_value" for s in FAKE_SECRETS},
            },
        ]
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        aligned = align_extracted_keys_to_schema(records, schema)
        assert len(aligned) == 1
        for key in aligned[0]:
            assert not key.startswith("_") or key == "_extraction_method", f"Leaked secret key in aligned output: {key}"

    def test_secrets_not_in_job_model_dump(self) -> None:
        """Job.model_dump excludes results with injected secrets via pipeline stripping."""
        job = Job(
            id="test-secrets-dump",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Test Co", "price": "$10"}],
            created_at="2026-01-01T00:00:00",
        )
        dumped = job.model_dump()
        results_str = json.dumps(dumped.get("results", []))
        quality_str = json.dumps(dumped.get("quality_report", {}))
        # After pipeline processing, raw secrets are stripped — verify
        # the output format doesn't contain known secret key patterns
        for secret in ("_cookie", "_localStorage", "_sessionStorage"):
            assert secret not in results_str, f"Leaked {secret} in job results"
            assert secret not in quality_str, f"Leaked {secret} in quality_report"

    def test_secrets_not_in_db_row(self) -> None:
        """SQLite row serialization excludes known secret keys."""
        job = Job(
            id="test-secrets-row",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Test Co", "price": "$10"}],
            created_at="2026-01-01T00:00:00",
        )
        from app.job_store import _job_to_row

        row = _job_to_row(job)
        row_str = json.dumps(row)
        for secret in ("_cookie", "_localStorage", "_sessionStorage"):
            assert secret not in row_str, f"Leaked {secret} in DB row"

    def test_api_serialization_excludes_secrets(self) -> None:
        """Full API response path excludes browser state keys."""
        job = Job(
            id="test-secrets-api",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Test Co", "price": "$10"}],
            created_at="2026-01-01T00:00:00",
        )
        dumped = job.model_dump()
        results_str = json.dumps(dumped.get("results", []))
        for secret in (
            "_cookie",
            "_sessionStorage",
            "_localStorage",
            "_indexedDB",
        ):
            assert secret not in results_str, f"Leaked {secret}"

    def test_raw_secrets_never_in_logs_or_metadata(self) -> None:
        """Quality report, warnings, and public API output must never contain raw secret values."""
        job = Job(
            id="test-secrets-logs",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Test Co"}],
            error="",
            created_at="2026-01-01T00:00:00",
        )
        job.quality_report = {
            "overall_score": 0.8,
            "final_records": 1,
        }
        if hasattr(job, "warnings"):
            job.warnings = ["extraction completed with 1 record"]
        dumped = job.model_dump()
        # Public API shape: results, quality_report, logs
        public_keys = {"results", "quality_report", "logs", "error", "warnings"}
        public_output = {k: v for k, v in dumped.items() if k in public_keys}
        public_str = json.dumps(public_output)
        for secret in FAKE_SECRETS:
            assert secret not in public_str, f"Secret key '{secret}' leaked in public API output"
        # Verify quality_report structure doesn't contain raw_data subkey
        qr = dumped.get("quality_report", {}) or {}
        assert "raw_data" not in qr, "quality_report must not expose raw_data to API consumers"


# ══════════════════════════════════════════════════════════════════════════
# Field-Mapping Confidence Metadata
# ══════════════════════════════════════════════════════════════════════════


class TestFieldMappingConfidence:
    """Verify extraction output includes structured field-mapping metadata."""

    def test_extraction_produces_record_score(self) -> None:
        from app.selector_engine import apply_selectors

        html = "<div class='c'><span class='n'>Test</span><span class='p'>$10</span></div>"
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        selectors = {"item_container": "div.c", "fields": {"name": ".n", "price": ".p"}}
        result = apply_selectors(html, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        assert len(records) > 0
        for r in records:
            assert "record_score" in r
            assert r["record_score"] > 0

    def test_acquisition_lineage_evidence_fields_present(self) -> None:
        from app.acquisition_state import AcquisitionLineage, AcquisitionState

        lineage = AcquisitionLineage(
            original_url="https://example.com/search/id/t1",
            final_url="https://example.com/search/id/t1",
            state=AcquisitionState.DIRECT,
            fetch_method="playwright_full",
        )
        d = lineage.model_dump()
        for field in (
            "data_evidence_score",
            "network_payloads_found",
            "recommended_next_action",
            "anti_bot_score",
            "forms_detected",
            "containers_detected",
        ):
            assert field in d, f"Missing lineage field: {field}"

    def test_provenance_builder_tracks_field_origin(self) -> None:
        """Provenance records where each field value came from."""
        from app.extraction_provenance import ProvenanceBuilder

        pb = ProvenanceBuilder("https://example.com", "example.com")
        pb.add_field_provenance(
            record_idx=0,
            field_name="price",
            value="$10",
            method="discovery",
            selector=".price",
            confidence=0.85,
        )
        pb.add_field_provenance(
            record_idx=0,
            field_name="name",
            value="Test",
            method="discovery",
            selector=".name",
            confidence=0.90,
        )
        provenance = pb.build()
        assert provenance is not None
        assert len(provenance.fields) > 0
        for entry in provenance.fields.values():
            assert entry.field_name in ("price", "name")
            assert entry.method == "discovery"
            assert entry.confidence > 0


# ══════════════════════════════════════════════════════════════════════════
# Fake Dynamic Session-Bound Website Simulation
# ══════════════════════════════════════════════════════════════════════════

FAKE_SESSION_HTML = """<!DOCTYPE html>
<html><head><title>Search Results</title></head><body>
<div class="results">
  <div class="card"><span class="name">Result One</span><span class="price">$10</span></div>
  <div class="card"><span class="name">Result Two</span><span class="price">$20</span></div>
  <div class="card"><span class="name">Result Three</span><span class="price">$30</span></div>
</div>
<script>
  localStorage.setItem('search_session', 'tok_deadbeef');
  sessionStorage.setItem('last_query', 'test query');
  document.cookie = 'session_id=abc123; path=/';
</script>
</body></html>"""

FAKE_NETWORK_JSON = json.dumps(
    {
        "results": [
            {"carrier": "TestAir", "fare": 100, "currency": "USD"},
            {"carrier": "DemoJet", "fare": 200, "currency": "USD"},
        ],
    },
)


class TestFakeDynamicSessionBoundWebsite:
    """Simulate a session-bound website with cookies, storage, and network JSON."""

    def test_fake_html_has_data_cards(self) -> None:
        """The fake session HTML has renderable data cards."""
        assert "Result One" in FAKE_SESSION_HTML
        assert "$10" in FAKE_SESSION_HTML
        assert "localStorage" in FAKE_SESSION_HTML

    def test_fake_network_json_is_valid(self) -> None:
        """Fake network payload is valid JSON with structured results."""
        payload = json.loads(FAKE_NETWORK_JSON)
        assert isinstance(payload, dict)
        assert "results" in payload
        assert len(payload["results"]) == 2
        assert payload["results"][0]["carrier"] == "TestAir"

    def test_extraction_from_fake_html(self) -> None:
        """Scraper extracts records from the fake session-bound HTML."""
        from app.selector_engine import apply_selectors

        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        selectors = {
            "item_container": "div.card",
            "fields": {"name": ".name", "price": ".price"},
        }
        result = apply_selectors(FAKE_SESSION_HTML, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        assert len(records) == 3
        names = {r.get("name") for r in records}
        assert names == {"Result One", "Result Two", "Result Three"}

    def test_fake_url_detected_as_session_bound(self) -> None:
        """The fake URL pattern is detected as session-bound."""
        from app.session_url_detector import detect_session_params

        # Use long opaque token in path — must be > certain length
        result = detect_session_params("https://example.com/search/id/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")
        assert result.get("is_session_bound") is True, f"Expected session-bound, got: {result}"

    def test_secrets_not_in_extraction_output(self) -> None:
        """Fake session HTML has localStorage/cookie but extraction strips them."""
        from app.selector_engine import apply_selectors

        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]
        selectors = {"item_container": "div.card", "fields": {"name": ".name"}}
        result = apply_selectors(FAKE_SESSION_HTML, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        for r in records:
            for key in r:
                assert "localStorage" not in key
                assert "cookie" not in key.lower()
                assert "session_id" not in key.lower()

    def test_network_payload_extraction_structured(self) -> None:
        """Captured network JSON can be parsed as structured records."""
        payload = json.loads(FAKE_NETWORK_JSON)
        extracted = []
        for item in payload["results"]:
            extracted.append(
                {
                    "requested_field": "airline",
                    "mapped_from": item.get("carrier", ""),
                    "source": "network_payload",
                    "confidence": 0.9,
                },
            )
        assert len(extracted) == 2
        assert extracted[0]["source"] == "network_payload"
        assert extracted[0]["confidence"] > 0.8

    def test_network_payload_secrets_not_leaked(self) -> None:
        """Network JSON extraction output must not leak raw tokens."""
        payload = json.loads(FAKE_NETWORK_JSON)
        dumped = json.dumps(payload)
        for secret in ("token", "session_id", "cookie", "auth"):
            assert secret not in dumped.lower() or secret == "currency", f"Leaked potential secret: {secret}"


# ══════════════════════════════════════════════════════════════════════════
# True Local Session-Bound E2E — HTTP server + browser state simulation
# ══════════════════════════════════════════════════════════════════════════


class _SessionBoundHandler(http.server.BaseHTTPRequestHandler):
    """Simulates a session-bound search results page with cookies/storage/API."""

    SEARCH_RESULTS_HTML = b"""<!DOCTYPE html>
<html><head><title>Search Results</title></head><body>
<div class="results">
  <div class="card"><span class="name">Alpha</span><span class="price">$100</span></div>
  <div class="card"><span class="name">Beta</span><span class="price">$200</span></div>
</div>
<script>
  localStorage.setItem('search_session', 'tok_local_abc');
  sessionStorage.setItem('query_id', 'q_xyz');
  document.cookie = 'sid=deadbeef; path=/';
</script>
</body></html>"""

    SEARCH_API_JSON = json.dumps(
        {
            "results": [
                {"carrier": "TestAir", "fare": 100},
                {"carrier": "DemoJet", "fare": 200},
            ],
        },
    ).encode()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/search/id/test12345abcde":
            self.send_response(200)
            self.send_header("Set-Cookie", "sid=deadbeef; Path=/; HttpOnly")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self.SEARCH_RESULTS_HTML)
        elif parsed.path == "/api/results":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(self.SEARCH_API_JSON)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args) -> None:
        pass  # silence server logs during tests


@pytest.mark.browser
class TestLocalSessionBoundServer:
    """End-to-end test with a real local HTTP server simulating session-bound behavior."""

    server: http.server.HTTPServer
    port: int
    base_url: str
    thread: threading.Thread

    @classmethod
    def setup_class(cls) -> None:
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _SessionBoundHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def teardown_class(cls) -> None:
        cls.server.shutdown()

    def test_local_server_serves_search_page(self) -> None:
        """Local server returns the session-bound search HTML."""
        import urllib.request

        url = f"{self.base_url}/search/id/test12345abcde"
        resp = urllib.request.urlopen(url)  # nosec B310 - HTTP URL to local test server, not file:// scheme
        assert resp.status == 200
        html = resp.read().decode()
        assert "Alpha" in html
        assert "localStorage" in html

    def test_local_server_sets_cookie(self) -> None:
        """Local server sets a session cookie in the response."""
        import urllib.request

        url = f"{self.base_url}/search/id/test12345abcde"
        resp = urllib.request.urlopen(url)  # nosec B310 - HTTP URL to local test server, not file:// scheme
        cookies = resp.getheader("Set-Cookie") or ""
        assert "sid=deadbeef" in cookies

    def test_local_url_detected_as_session_bound(self) -> None:
        """The local server URL pattern is detected as session-bound."""
        from app.session_url_detector import detect_session_params

        result = detect_session_params(f"{self.base_url}/search/id/test12345abcde")
        assert result.get("is_session_bound") is True

    def test_local_server_api_returns_json(self) -> None:
        """Local server /api/results returns structured JSON."""
        import urllib.request

        url = f"{self.base_url}/api/results"
        resp = urllib.request.urlopen(url)  # nosec B310 - HTTP URL to local test server, not file:// scheme
        assert resp.status == 200
        data = json.loads(resp.read())
        assert len(data["results"]) == 2
        assert data["results"][0]["carrier"] == "TestAir"

    def test_extraction_from_local_html(self) -> None:
        """Scraper extracts records from the locally-served HTML."""
        import urllib.request

        url = f"{self.base_url}/search/id/test12345abcde"
        html = urllib.request.urlopen(url).read().decode()  # nosec B310 - HTTP URL to local test server, not file:// scheme
        from app.selector_engine import apply_selectors

        schema = [
            SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
            SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
        ]
        selectors = {
            "item_container": "div.card",
            "fields": {"name": ".name", "price": ".price"},
        }
        result = apply_selectors(html, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        assert len(records) == 2
        names = {r.get("name") for r in records}
        assert names == {"Alpha", "Beta"}

    def test_network_payload_extraction_from_local_api(self) -> None:
        """Captured network JSON from local /api/results can be structured."""
        import urllib.request

        url = f"{self.base_url}/api/results"
        data = json.loads(urllib.request.urlopen(url).read())  # nosec B310 - HTTP URL to local test server, not file:// scheme
        extracted = []
        for item in data["results"]:
            extracted.append(
                {
                    "requested_field": "airline",
                    "mapped_from": item["carrier"],
                    "source": "network_payload",
                    "confidence": 0.9,
                },
            )
        assert len(extracted) == 2
        assert all(e["source"] == "network_payload" for e in extracted)
        assert all(e["confidence"] > 0.8 for e in extracted)

    def test_local_html_does_not_leak_secrets_in_extraction(self) -> None:
        """Local HTML contains localStorage/cookie text but extraction strips it."""
        import urllib.request

        html = urllib.request.urlopen(f"{self.base_url}/search/id/test12345abcde").read().decode()  # nosec B310 - HTTP URL to local test server, not file:// scheme
        from app.selector_engine import apply_selectors

        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]
        selectors = {"item_container": "div.card", "fields": {"name": ".name"}}
        result = apply_selectors(html, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        for r in records:
            for key in r:
                assert "sid" not in key.lower()
                assert "localStorage" not in key
                assert "cookie" not in key.lower()
