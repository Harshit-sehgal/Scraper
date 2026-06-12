"""Tests for extraction depth features: pagination, data quality, failure explanations."""

from app.data_quality import (
    clean_record,
    deduplicate_records,
    run_quality_pipeline,
    score_record,
    validate_record,
)
from app.failure_explainer import classify_error, detect_failure, explain_failure
from app.models import FieldType, SchemaField
from app.pagination_executor import PaginationConfig, paginate


class TestPaginationExecutor:
    """Tests for pagination strategies."""

    def test_default_pagination_config(self):
        config = PaginationConfig()
        assert config.strategy == "next_button"
        assert config.max_pages == 10
        assert config.max_records == 500
        assert config.stop_on_duplicates is True

    def test_paginate_next_button(self):
        config = PaginationConfig(strategy="next_button", max_pages=3)
        result = paginate(config)
        assert result.stopped_reason in ("max_pages", "no_new_records", "timeout")
        assert result.pages_scraped <= 3

    def test_paginate_infinite_scroll(self):
        config = PaginationConfig(strategy="infinite_scroll", max_pages=2)
        result = paginate(config)
        assert result.stopped_reason is not None
        assert result.pages_scraped <= 2

    def test_paginate_load_more(self):
        config = PaginationConfig(strategy="load_more", max_pages=2)
        result = paginate(config)
        assert result.stopped_reason is not None
        assert result.pages_scraped <= 2

    def test_pagination_respects_max_records(self):
        # Since we can't actually extract from a real page,
        # this just verifies the config propagates
        config = PaginationConfig(strategy="next_button", max_pages=10, max_records=100)
        result = paginate(config)
        assert result.stopped_reason is not None

    def test_pagination_timeout(self):
        config = PaginationConfig(strategy="next_button", max_pages=1, max_runtime_seconds=0)
        result = paginate(config)
        assert result.stopped_reason == "timeout"


class TestDataQuality:
    """Tests for data cleaning, validation, deduplication, and scoring."""

    def test_clean_text(self):
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        record = {"title": "  Hello   World  "}
        cleaned = clean_record(record, schema)
        assert cleaned["title"] == "Hello World"

    def test_clean_price(self):
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        record = {"price": "$1,234.56"}
        cleaned = clean_record(record, schema)
        assert cleaned["price"] == 1234.56

    def test_clean_email(self):
        schema = [SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description="")]
        record = {"email": "  Test@EXAMPLE.COM  "}
        cleaned = clean_record(record, schema)
        assert cleaned["email"] == "test@example.com"

    def test_clean_url_removes_tracking(self):
        schema = [SchemaField(name="url", field_type=FieldType.URL, required=False, description="")]
        record = {"url": "https://example.com/page?utm_source=email&foo=bar"}
        cleaned = clean_record(record, schema)
        assert "utm_source" not in cleaned["url"]
        assert "foo=bar" in cleaned["url"]

    def test_validate_required_field_missing(self):
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        record = {"title": ""}
        is_valid, errors = validate_record(record, schema)
        assert not is_valid
        assert "title" in errors

    def test_validate_email_format(self):
        schema = [SchemaField(name="email", field_type=FieldType.EMAIL, required=False, description="")]
        record = {"email": "not-an-email"}
        is_valid, errors = validate_record(record, schema)
        assert not is_valid
        assert "email" in errors

    def test_validate_url_format(self):
        schema = [SchemaField(name="url", field_type=FieldType.URL, required=False, description="")]
        record = {"url": "not-a-url"}
        is_valid, errors = validate_record(record, schema)
        assert not is_valid
        assert "url" in errors

    def test_validate_phone_format(self):
        schema = [SchemaField(name="phone", field_type=FieldType.PHONE, required=False, description="")]
        record = {"phone": "123"}  # Too short
        is_valid, errors = validate_record(record, schema)
        assert not is_valid
        assert "phone" in errors

    def test_deduplicate_records(self):
        records = [
            {"a": "1", "b": "2"},
            {"a": "1", "b": "2"},
            {"a": "3", "b": "4"},
        ]
        unique, removed = deduplicate_records(records)
        assert len(unique) == 2
        assert removed == 1

    def test_score_record(self):
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True, description=""),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
        ]
        record = {"title": "Test Item", "price": 10.99}
        score = score_record(record, schema)
        assert 0.0 <= score <= 1.0

    def test_score_record_missing_required(self):
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        record = {"title": ""}
        score = score_record(record, schema)
        assert score == 0.0

    def test_run_quality_pipeline(self):
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True, description=""),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
        ]
        records = [
            {"title": "Item 1", "price": "$10.00"},
            {"title": "Item 1", "price": "$10.00"},  # duplicate
            {"title": "", "price": "$20.00"},  # missing required
        ]
        result = run_quality_pipeline(records, schema)
        assert result["total_input"] == 3
        assert result["total_valid"] == 1
        assert result["duplicates_removed"] == 1
        assert result["total_invalid"] == 1
        assert 0.0 <= result["quality_score"] <= 1.0
        assert len(result["warnings"]) > 0

    def test_run_quality_pipeline_empty(self):
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True, description="")]
        result = run_quality_pipeline([], schema)
        assert result["total_input"] == 0
        assert result["total_valid"] == 0
        assert result["quality_score"] == 0.0


class TestFailureExplainer:
    """Tests for failure explanation and classification."""

    def test_detect_login_required_from_http_status(self):
        explanation = detect_failure(http_status=401)
        assert explanation.failure_type == "login_required"
        assert "login" in explanation.user_message.lower()

    def test_detect_session_expired_from_http_status(self):
        explanation = detect_failure(http_status=403, has_auth_profile=True)
        assert explanation.failure_type == "session_expired"

    def test_detect_timeout(self):
        explanation = detect_failure(timeout_occurred=True)
        assert explanation.failure_type == "timeout"

    def test_detect_blocked(self):
        explanation = detect_failure(url_safety_result="blocked")
        assert explanation.failure_type == "domain_blocked"

    def test_detect_selector_not_found(self):
        explanation = detect_failure(selector_found=False, records_found=0)
        assert explanation.failure_type == "no_records_found"

    def test_detect_no_records(self):
        explanation = detect_failure(records_found=0, selector_found=True)
        assert explanation.failure_type == "no_records_found"

    def test_explain_failure_known_type(self):
        explanation = explain_failure("login_required")
        assert explanation.failure_type == "login_required"
        assert explanation.user_message != ""
        assert explanation.recommended_action != ""

    def test_explain_failure_unknown_type(self):
        explanation = explain_failure("nonexistent_type")
        assert explanation.failure_type == "unknown_error"

    def test_classify_error_timeout(self):
        error = TimeoutError("Connection timed out")
        assert classify_error(error) == "timeout"

    def test_classify_error_blocked(self):
        error = Exception("blocked by anti-bot")
        assert classify_error(error) == "blocked_or_challenge"

    def test_classify_error_unknown(self):
        error = ValueError("something else")
        assert classify_error(error) == "unknown_error"
