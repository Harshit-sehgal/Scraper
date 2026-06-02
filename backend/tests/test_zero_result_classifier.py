"""
Tests for Zero-Result Failure Classifier.

Tests cover all nine failure categories, confidence range validation,
and user message integrity.
"""

from __future__ import annotations

import pytest
from app.zero_result_classifier import _any_field_matches_page, _has_auth_patterns, classify_zero_result

VALID_FAILURE_CLASSES = {
    "session_bound_url",
    "search_replay_required",
    "auth_required",
    "empty_response",
    "anti_bot_block",
    "js_render_required",
    "selector_failure",
    "schema_mismatch",
    "genuinely_empty",
}


class TestZeroResultClassification:
    def test_empty_page_detected_by_empty_check(self):
        empty_check = {"is_empty": True, "confidence": 0.90}
        result = classify_zero_result(empty_check=empty_check)
        assert result.failure_class == "empty_response"
        assert result.zero_result is True

    def test_empty_page_below_confidence_threshold_is_skipped(self):
        empty_check = {"is_empty": True, "confidence": 0.40}
        result = classify_zero_result(
            empty_check=empty_check,
            html="<html>" + "x" * 200 + "</html>",
            visible_text="some content",
            detected_containers=1,
            raw_candidate_count=1,
        )
        assert result.failure_class != "empty_response"

    def test_high_anti_bot_score(self):
        result = classify_zero_result(anti_bot_score=0.95)
        assert result.failure_class == "anti_bot_block"

    def test_anti_bot_score_at_threshold(self):
        result = classify_zero_result(anti_bot_score=0.80)
        assert result.failure_class == "anti_bot_block"

    def test_anti_bot_score_below_threshold(self):
        result = classify_zero_result(anti_bot_score=0.70)
        assert result.failure_class != "anti_bot_block"

    def test_session_bound_url_with_forms(self):
        session_detection = {"is_session_bound": True, "confidence": 0.75}
        result = classify_zero_result(
            session_detection=session_detection,
            detected_forms=[{"action": "/search", "method": "GET"}],
        )
        assert result.failure_class == "session_bound_url"

    def test_session_bound_url_without_forms(self):
        session_detection = {"is_session_bound": True, "confidence": 0.75}
        result = classify_zero_result(
            session_detection=session_detection,
            detected_forms=[],
        )
        assert result.failure_class == "search_replay_required"

    def test_blank_html_classified_as_empty_response(self):
        result = classify_zero_result(html="<html></html>")
        assert result.failure_class == "empty_response"
        assert result.confidence >= 0.90

    def test_login_page_with_auth_text(self):
        result = classify_zero_result(
            visible_text="Please login to continue. Enter your password below.",
            html="<html>" + "x" * 200 + "</html>",
        )
        assert result.failure_class == "auth_required"

    def test_login_page_with_sign_in_text(self):
        result = classify_zero_result(
            visible_text="Sign in to view your dashboard",
            html="<html>" + "x" * 200 + "</html>",
        )
        assert result.failure_class == "auth_required"

    def test_js_shell_long_html_no_containers(self):
        result = classify_zero_result(
            html="<html>" + "x" * 2000 + "</html>",
            detected_containers=0,
            raw_candidate_count=5,
        )
        assert result.failure_class == "js_render_required"

    def test_js_shell_not_triggered_without_candidates(self):
        result = classify_zero_result(
            html="<html>" + "x" * 2000 + "</html>",
            detected_containers=0,
            raw_candidate_count=0,
        )
        assert result.failure_class != "js_render_required"

    def test_selector_failure_containers_no_candidates(self):
        result = classify_zero_result(
            html="<html>" + "x" * 200 + "</html>",
            detected_containers=5,
            raw_candidate_count=0,
        )
        assert result.failure_class == "selector_failure"

    def test_schema_mismatch_no_fields_on_page(self):
        result = classify_zero_result(
            schema_fields=["company_name", "annual_revenue", "employee_count"],
            html="<html>" + "x" * 500 + "<p>This page is about weather and gardening tips</p></html>",
            visible_text="This page is about weather and gardening tips",
        )
        assert result.failure_class == "schema_mismatch"

    def test_schema_mismatch_not_triggered_when_fields_present(self):
        result = classify_zero_result(
            schema_fields=["company_name"],
            html="<html>" + "x" * 200 + "company_name" + "x" * 200 + "</html>",
            visible_text="company_name",
        )
        assert result.failure_class != "schema_mismatch"

    def test_default_falls_back_to_genuinely_empty(self):
        result = classify_zero_result(
            html="<html>" + "x" * 500 + "</html>",
            visible_text="Some generic page content with no special patterns",
            detected_containers=3,
            raw_candidate_count=3,
        )
        assert result.failure_class == "genuinely_empty"

    def test_empty_check_has_priority_over_anti_bot(self):
        empty_check = {"is_empty": True, "confidence": 0.90}
        result = classify_zero_result(
            empty_check=empty_check,
            anti_bot_score=0.95,
        )
        assert result.failure_class == "empty_response"

    def test_anti_bot_has_priority_over_session(self):
        session_detection = {"is_session_bound": True, "confidence": 0.75}
        result = classify_zero_result(
            session_detection=session_detection,
            detected_forms=[{"action": "/search"}],
            anti_bot_score=0.90,
        )
        assert result.failure_class == "anti_bot_block"

    def test_session_has_priority_over_auth(self):
        session_detection = {"is_session_bound": True, "confidence": 0.75}
        result = classify_zero_result(
            session_detection=session_detection,
            detected_forms=[],
            visible_text="Please login with your password",
            html="<html>" + "x" * 200 + "</html>",
        )
        assert result.failure_class == "search_replay_required"

    def test_auth_has_priority_over_js_shell(self):
        result = classify_zero_result(
            html="<html>" + "x" * 2000 + "</html>",
            visible_text="Please login to continue. Enter your password",
            detected_containers=0,
            raw_candidate_count=5,
        )
        assert result.failure_class == "auth_required"

    def test_js_shell_has_priority_over_selector_failure(self):
        result = classify_zero_result(
            html="<html>" + "x" * 2000 + "</html>",
            detected_containers=0,
            raw_candidate_count=5,
        )
        assert result.failure_class == "js_render_required"

    def test_selector_failure_has_priority_over_schema_mismatch(self):
        result = classify_zero_result(
            html="<html>" + "x" * 200 + "</html>",
            schema_fields=["company_name"],
            detected_containers=5,
            raw_candidate_count=0,
        )
        assert result.failure_class == "selector_failure"

    def test_schema_mismatch_has_priority_over_genuinely_empty(self):
        result = classify_zero_result(
            html="<html>" + "x" * 500 + "</html>",
            visible_text="generic content",
            schema_fields=["company_name"],
            detected_containers=3,
            raw_candidate_count=1,
        )
        assert result.failure_class == "schema_mismatch"


class TestConfidenceRange:
    def test_anti_bot_confidence_in_range(self):
        result = classify_zero_result(anti_bot_score=0.90)
        assert 0.0 <= result.confidence <= 1.0

    def test_session_confidence_in_range(self):
        result = classify_zero_result(
            session_detection={"is_session_bound": True, "confidence": 0.75},
            detected_forms=[{"action": "/search"}],
        )
        assert 0.0 <= result.confidence <= 1.0

    def test_empty_page_confidence_in_range(self):
        result = classify_zero_result(html="<html></html>")
        assert 0.0 <= result.confidence <= 1.0

    def test_auth_confidence_in_range(self):
        result = classify_zero_result(
            visible_text="Please login with your password",
            html="<html>" + "x" * 200 + "</html>",
        )
        assert 0.0 <= result.confidence <= 1.0

    def test_default_confidence_in_range(self):
        result = classify_zero_result(
            html="<html>" + "x" * 500 + "</html>",
            visible_text="some content",
            detected_containers=2,
            raw_candidate_count=1,
        )
        assert 0.0 <= result.confidence <= 1.0


class TestUserMessages:
    def test_all_failure_classes_have_messages(self):
        from app.zero_result_classifier import _MESSAGES

        for fc in VALID_FAILURE_CLASSES:
            msg = _MESSAGES[fc]
            assert isinstance(msg["user_message"], str) and len(msg["user_message"]) > 0
            assert isinstance(msg["operator_hint"], str) and len(msg["operator_hint"]) > 0
            assert isinstance(msg["recommended_action"], str) and len(msg["recommended_action"]) > 0

    @pytest.mark.parametrize(
        "kwargs,expected_class",
        [
            ({"anti_bot_score": 0.90}, "anti_bot_block"),
            ({"empty_check": {"is_empty": True, "confidence": 0.90}}, "empty_response"),
            ({"visible_text": "Please login with password", "html": "x" * 200}, "auth_required"),
            ({"session_detection": {"is_session_bound": True}, "detected_forms": [{"action": "/x"}]}, "session_bound_url"),
            ({"session_detection": {"is_session_bound": True}, "detected_forms": []}, "search_replay_required"),
            ({"html": "x" * 2000, "detected_containers": 0, "raw_candidate_count": 5}, "js_render_required"),
            ({"html": "x" * 200, "detected_containers": 5, "raw_candidate_count": 0}, "selector_failure"),
            ({"schema_fields": ["company_name"], "html": "x" * 500, "visible_text": "x"}, "schema_mismatch"),
            (
                {"html": "x" * 500, "visible_text": "some text", "detected_containers": 1, "raw_candidate_count": 1},
                "genuinely_empty",
            ),
        ],
    )
    def test_user_messages_are_non_empty(self, kwargs, expected_class):
        result = classify_zero_result(**kwargs)
        assert result.failure_class == expected_class
        assert isinstance(result.user_message, str) and len(result.user_message) > 0
        assert isinstance(result.operator_hint, str) and len(result.operator_hint) > 0
        assert isinstance(result.recommended_action, str) and len(result.recommended_action) > 0


class TestHelperFunctions:
    def test_auth_patterns_case_insensitive(self):
        assert _has_auth_patterns("Please LOGIN here")
        assert _has_auth_patterns("Sign In With Google")
        assert _has_auth_patterns("New PASSWORD required")

    def test_auth_patterns_not_matched(self):
        assert not _has_auth_patterns("Welcome to our store")
        assert not _has_auth_patterns("")
        assert not _has_auth_patterns("Browse our catalog of products")

    def test_field_matches_page(self):
        assert _any_field_matches_page(
            ["company_name"],
            "<html><body>Company_Name</body></html>",
            "Company_Name",
        )
        assert _any_field_matches_page(
            ["price", "title"],
            "<html>some html</html>",
            "Click here for the lowest price",
        )
        assert not _any_field_matches_page(
            ["company_name"],
            "<html>weather report</html>",
            "weather report for today",
        )


class TestToDict:
    def test_to_dict_returns_all_keys(self):
        result = classify_zero_result(anti_bot_score=0.90)
        d = result.to_dict()
        assert d["zero_result"] is True
        assert d["failure_class"] == "anti_bot_block"
        assert isinstance(d["confidence"], float)
        assert isinstance(d["user_message"], str)
        assert isinstance(d["operator_hint"], str)
        assert isinstance(d["recommended_action"], str)


class TestNoneInputs:
    def test_all_none_inputs_defaults_to_genuinely_empty(self):
        result = classify_zero_result(
            html="<html>" + "x" * 500 + "</html>",
            visible_text="some content",
            detected_containers=1,
            raw_candidate_count=1,
        )
        assert result.failure_class == "genuinely_empty"
        assert result.zero_result is True

    def test_none_detected_forms_treated_as_empty(self):
        session_detection = {"is_session_bound": True, "confidence": 0.75}
        result = classify_zero_result(
            session_detection=session_detection,
            detected_forms=None,
        )
        assert result.failure_class == "search_replay_required"

    def test_none_html_and_visible_text(self):
        result = classify_zero_result(
            html=None,
            visible_text=None,
        )
        assert result.failure_class == "empty_response"
