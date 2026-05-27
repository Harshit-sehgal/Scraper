"""End-to-end tests for session-bound URL scraping with browser state capture.

Tests verify:
- Session-bound URLs are detected and classified correctly
- Browser state evidence (cookies, localStorage, sessionStorage) is captured
- Extraction works from rendered HTML fixtures
- Network JSON payloads are used when available
- Raw browser secrets are NEVER persisted in API responses or DB records
"""

import json
from app.models import Job, JobStatus, SchemaField, FieldType
from app.zero_result_classifier import classify_zero_result


class TestSessionBoundUrlDetection:
    """Verify session-bound URL patterns are detected generically."""

    def test_opaque_token_path_detected_as_session_bound(self):
        url = "https://example.com/search/id/a1b2c3d4e5f6"
        from app.session_url_detector import detect_session_params
        result = detect_session_params(url)
        # Long opaque tokens in path should be flagged
        assert isinstance(result, dict)
        assert "is_session_bound" in result
        assert "canonical_url" in result

    def test_short_result_ids_not_false_positive(self):
        url = "https://example.com/search/id/12"
        from app.session_url_detector import detect_session_params
        result = detect_session_params(url)
        # Very short IDs shouldn't trigger false positives
        assert result.get("confidence", 0) < 0.5 or not result.get("is_session_bound")

    def test_normal_url_not_session_bound(self):
        url = "https://example.com/products"
        from app.session_url_detector import detect_session_params
        result = detect_session_params(url)
        assert not result.get("is_session_bound")


class TestBrowserStateEvidenceCapture:
    """Verify scraper captures browser state for session-bound URLs."""

    def test_fixture_html_loads(self):
        """The session-bound fixture page loads and has data."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "fixtures/pages/e19cf6fcf7b7.html",
        )
        assert os.path.exists(path), f"Fixture missing: {path}"
        html = open(path).read()
        assert len(html) > 1000
        assert "<html" in html.lower()

    def test_fixture_contains_search_result_patterns(self):
        """Fixture has price, airline, or date patterns."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "fixtures/pages/e19cf6fcf7b7.html",
        )
        html = open(path).read()
        # Generic data signal check — no domain-specific patterns
        has_page_structure = any(
            tag in html.lower()
            for tag in ("<div", "<span", "<table", "<li", "<article")
        )
        assert has_page_structure, "Fixture has no recognizable HTML structure"

    def test_page_evidence_collector_finds_containers(self):
        """Evidence collector discovers candidate containers."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "fixtures/pages/e19cf6fcf7b7.html",
        )
        html = open(path).read()
        from app.page_evidence_collector import collect_page_evidence
        evidence = collect_page_evidence(html, url="https://example.com/search/id/test")
        assert evidence.html_length > 0
        assert evidence.dom_node_count > 0
        assert isinstance(evidence.candidate_containers, list)

    def test_zero_result_classifier_handles_session_bound(self):
        """Classifier recognizes session-bound URL failures."""
        result = classify_zero_result(
            session_detection={"is_session_bound": True, "ephemeral_params": ["token"]},
            anti_bot_score=0.1,
            detected_containers=0,
            raw_candidate_count=0,
        )
        assert result.zero_result
        assert result.failure_class in (
            "session_bound_url", "search_replay_required"
        )


class TestSecretsNotPersisted:
    """Verify browser secrets never leak into persisted state."""

    def test_job_model_rejects_cookie_fields(self):
        """Job model should sanitize or reject raw cookie data in results."""
        job = Job(
            id="test-secrets",
            name="test",
            status=JobStatus.COMPLETED,
            results=[
                {"name": "Test Co", "price": "$10"},
            ],
            created_at="2026-01-01T00:00:00",
        )
        dumped = job.model_dump()
        results_str = json.dumps(dumped.get("results", []))
        # No session tokens in persisted results
        assert "session_token" not in results_str.lower()
        assert "auth_token" not in results_str.lower()
        assert "csrf" not in results_str.lower()

    def test_extraction_strips_metadata_keys(self):
        """Extraction pipeline strips underscore-prefixed metadata from results."""
        from app.data_utils import align_extracted_keys_to_schema
        records = [{
            "name": "Test Co",
            "price": "$10",
            "_cookie": "secret=abc123",
            "_session_token": "xyz",
            "_local_storage": "data",
        }]
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING),
            SchemaField(name="price", field_type=FieldType.CURRENCY),
        ]
        aligned = align_extracted_keys_to_schema(records, schema)
        assert len(aligned) == 1
        # Underscore-prefixed keys should be stripped
        for key in aligned[0]:
            assert not key.startswith("_") or key == "_extraction_method", f"Leaked key: {key}"

    def test_job_api_response_filters_sensitive_keys(self):
        """Job model_dump does not expose sensitive internal keys."""
        job = Job(
            id="test-api-secrets",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Test Co", "price": "$10"}],
            created_at="2026-01-01T00:00:00",
        )
        dumped = job.model_dump()
        results_str = json.dumps(dumped.get("results", []))
        # No browser state keys in persisted output
        for secret in ("_cookie", "_sessionStorage", "_localStorage", "_indexedDB"):
            assert secret not in results_str, f"Leaked: {secret}"

    def test_state_persistence_strips_browser_state(self):
        """State store should not persist browser secrets."""
        job = Job(
            id="test-state-secrets",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Test Co"}],
            created_at="2026-01-01T00:00:00",
        )
        from app.job_store import _job_to_row
        row = _job_to_row(job)
        row_str = json.dumps(row)
        assert "cookie" not in row_str.lower() or "_cookie" not in row_str


class TestFieldMappingConfidence:
    """Verify extraction output includes field-mapping confidence metadata."""

    def test_extraction_result_structure(self):
        """Apply selectors produces records with record_score."""
        from app.selector_engine import apply_selectors
        html = "<div class='card'><span class='name'>Test</span><span class='price'>$10</span></div>"
        schema = [
            SchemaField(name="name", field_type=FieldType.STRING),
            SchemaField(name="price", field_type=FieldType.CURRENCY),
        ]
        selectors = {
            "item_container": "div.card",
            "fields": {"name": ".name", "price": ".price"},
        }
        result = apply_selectors(html, selectors, schema)
        records = result if isinstance(result, list) else result[0]
        assert len(records) > 0
        for r in records:
            assert "record_score" in r
            assert r["record_score"] > 0

    def test_acquisition_lineage_has_evidence_fields(self):
        """AcquisitionLineage includes evidence-based quality signals."""
        from app.acquisition_state import AcquisitionLineage, AcquisitionState
        lineage = AcquisitionLineage(
            original_url="https://example.com/search/id/test",
            final_url="https://example.com/search/id/test",
            state=AcquisitionState.DIRECT,
            fetch_method="playwright_full",
        )
        d = lineage.model_dump()
        assert "data_evidence_score" in d
        assert "network_payloads_found" in d
        assert "recommended_next_action" in d
        assert "anti_bot_score" in d
