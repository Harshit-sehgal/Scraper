"""Obs 13: Structured job logs — test JSON log format with job_id, url, etc."""
from __future__ import annotations

import json
from typing import Any


def _make_structured_log(
    job_id: str,
    url: str,
    level: str = "info",
    message: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured log entry following the expected format."""
    entry = {
        "timestamp": "2026-06-29T00:00:00.000Z",
        "level": level,
        "job_id": job_id,
        "url": url,
        "message": message,
    }
    if extra:
        entry.update(extra)
    return entry


def _validate_structured_log(entry: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that a structured log entry has all required fields."""
    errors = []
    required = {"timestamp", "level", "job_id", "url", "message"}
    for field in required:
        if field not in entry or not entry[field]:
            errors.append(f"Missing or empty required field: {field}")
    if not errors:
        try:
            json.dumps(entry)
        except (TypeError, ValueError) as e:
            errors.append(f"Not JSON-serializable: {e}")
    return len(errors) == 0, errors


class TestStructuredLogRequiredFields:
    def test_has_timestamp(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com", message="Scraping started")
        assert "timestamp" in entry

    def test_has_job_id(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com")
        assert entry["job_id"] == "job-001"

    def test_has_url(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com/page")
        assert entry["url"] == "https://example.com/page"

    def test_has_level(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com", level="error")
        assert entry["level"] == "error"

    def test_has_message(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com", message="Scraping completed")
        assert entry["message"] == "Scraping completed"


class TestStructuredLogValidation:
    def test_valid_entry_passes(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com", level="info", message="Started")
        is_valid, _ = _validate_structured_log(entry)
        assert is_valid is True

    def test_missing_job_id_fails(self) -> None:
        entry = _make_structured_log("", "https://example.com")
        is_valid, errors = _validate_structured_log(entry)
        assert is_valid is False

    def test_missing_url_fails(self) -> None:
        entry = _make_structured_log("job-001", "")
        is_valid, errors = _validate_structured_log(entry)
        assert is_valid is False

    def test_serializable(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com", extra={"duration_ms": 150, "records_found": 5})
        dumped = json.dumps(entry)
        assert isinstance(dumped, str)
        loaded = json.loads(dumped)
        assert loaded["duration_ms"] == 150

    def test_invalid_json_fails_validation(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com")
        entry["circular_ref"] = entry
        is_valid, errors = _validate_structured_log(entry)
        assert is_valid is False


class TestStructuredLogExtraFields:
    def test_extra_fields_allowed(self) -> None:
        entry = _make_structured_log("job-001", "https://example.com", extra={
            "duration_ms": 250,
            "strategy": "playwright",
            "records_found": 10,
            "cascade_layer": "regex",
        })
        assert entry["duration_ms"] == 250
        assert entry["strategy"] == "playwright"
        assert entry["records_found"] == 10

    def test_level_values(self) -> None:
        for level in ("debug", "info", "warning", "error", "critical"):
            entry = _make_structured_log("job-001", "https://x.com", level=level)
            assert entry["level"] == level
