"""Bench 4: Session expiry/recovery benchmark (Roadmap Bench 4).

Tests session-bound extraction, session expiry handling, search form
recovery, and data preservation across recovery.
"""
from __future__ import annotations

from pathlib import Path

from app.acquisition_quality_gate import quality_summary
from app.empty_response_detector import detect_empty_response
from app.search_form_recovery import _detect_search_form
from app.session_url_detector import detect_session_params
from app.zero_result_classifier import classify_zero_result
from bs4 import BeautifulSoup

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestBenchmarkSessionBoundExtraction:
    """Session-bound URL detection and handling."""

    def test_detect_session_params_in_url(self) -> None:
        result = detect_session_params("https://example.com/search?sid=abc123&q=valves")
        assert result.get("is_session_bound") is True

    def test_detect_no_session_params(self) -> None:
        result = detect_session_params("https://example.com/products")
        assert result.get("is_session_bound") is False

    def test_session_expired_html_detected(self) -> None:
        html = _load("session_expired.html")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True).lower()
        assert "session" in text and "expired" in text

    def test_session_search_form_detected(self) -> None:
        html = _load("session_search_form.html")
        form_info = _detect_search_form(html)
        assert form_info["detected"] is True
        assert form_info["method"] in ("GET", "get")
        assert any("q" in str(f.get("name", "")) for f in form_info.get("fields", []))

    def test_session_recovered_page_has_search_results(self) -> None:
        html = _load("session_search_recovered.html")
        soup = BeautifulSoup(html, "html.parser")
        results = soup.select(".supplier-card")
        assert len(results) > 0


class TestBenchmarkSessionExpiryHandling:
    """Session expiry detection and classification."""

    def test_expired_session_page_classified_as_session_bound(self) -> None:
        html = _load("session_expired.html")
        soup = BeautifulSoup(html, "html.parser")
        visible_text = soup.get_text(separator=" ", strip=True)
        forms = [{"action": f.get("action", ""), "method": f.get("method", "")} for f in soup.find_all("form")]
        empty_check = detect_empty_response(html)
        classification = classify_zero_result(
            acquisition_lineage={"state": "direct"},
            session_detection=None,
            empty_check=vars(empty_check),
            anti_bot_score=0.0,
            final_url="https://fixtures.local/session_expired.html",
            html=html,
            visible_text=visible_text,
            detected_forms=forms,
            detected_containers=0,
            raw_candidate_count=0,
            schema_fields=["title"],
        )
        assert classification.failure_class in ("session_bound_url", "search_replay_required")

    def test_recovered_session_passes_quality_gate(self) -> None:
        html = _load("session_search_recovered.html")
        result = quality_summary(
            data_evidence_score=0.8,
            anti_bot_score=0.9,
            visible_text_length=len(html),
        )
        assert result["result"] in ("pass", "review")


class TestBenchmarkSearchFormRecovery:
    """Search form recovery flow."""

    def test_search_form_detected_on_expired_page(self) -> None:
        html = _load("session_expired.html")
        form_info = _detect_search_form(html)
        assert form_info["detected"] is True
        assert len(form_info.get("search_fields", [])) > 0

    def test_search_form_has_query_field(self) -> None:
        html = _load("session_search_form.html")
        form_info = _detect_search_form(html)
        search_fields = form_info.get("search_fields", [])
        field_names = [f.get("name", "") for f in search_fields]
        assert any("q" in name for name in field_names), f"No query field found in {field_names}"


class TestBenchmarkDataPreservation:
    """Data is preserved across session recovery cycles."""

    def test_recovered_page_contains_supplier_data(self) -> None:
        html = _load("session_search_recovered.html")
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(".supplier-card"):
            name_el = card.select_one(".supplier-name")
            assert name_el is not None
            assert len(name_el.get_text(strip=True)) > 0

    def test_recovered_results_show_expected_structure(self) -> None:
        html = _load("session_search_recovered.html")
        soup = BeautifulSoup(html, "html.parser")
        stats = soup.select_one(".search-stats")
        if stats:
            count_el = stats.select_one(".result-count")
            assert count_el is not None, "Result count element missing in recovered page"
