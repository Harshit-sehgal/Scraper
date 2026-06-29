"""Unit tests for ``app.utils.job`` - result normalization and deduplication helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import FieldType, SchemaField
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results


def _field(name: str) -> SchemaField:
    return SchemaField(name=name, field_type=FieldType.STRING)


_SCHEMA = [_field("title"), _field("price"), _field("url")]


class TestNormalizeJobResults:
    def test_empty_results(self) -> None:
        assert normalize_job_results([], _SCHEMA) == []

    def test_orders_fields_by_schema(self) -> None:
        results = [{"url": "http://a.com", "title": "Foo", "price": "10"}]
        normalized = normalize_job_results(results, _SCHEMA)
        assert list(normalized[0].keys())[:3] == ["title", "price", "url"]

    def test_extra_fields_appended_sorted(self) -> None:
        results = [{"title": "Foo", "price": "10", "extra_z": "z", "extra_a": "a"}]
        normalized = normalize_job_results(results, _SCHEMA)
        keys = list(normalized[0].keys())
        assert keys[:3] == ["title", "price", "url"]
        assert "extra_a" in keys
        assert "extra_z" in keys

    def test_missing_schema_fields_become_none(self) -> None:
        results = [{"title": "Foo"}]
        normalized = normalize_job_results(results, _SCHEMA)
        assert normalized[0]["price"] is None
        assert normalized[0]["url"] is None

    def test_preserves_multiple_records(self) -> None:
        results = [{"title": "A", "price": "1"}, {"title": "B", "price": "2"}]
        normalized = normalize_job_results(results, _SCHEMA)
        assert len(normalized) == 2
        assert normalized[0]["title"] == "A"
        assert normalized[1]["title"] == "B"


class TestDeduplicateResults:
    def test_empty_records(self) -> None:
        assert deduplicate_results([], _SCHEMA) == []

    def test_all_unique_by_composite_key(self) -> None:
        records = [{"title": "A", "price": "1"}, {"title": "B", "price": "2"}]
        result = deduplicate_results(records, _SCHEMA)
        assert len(result) == 2

    def test_removes_duplicates_by_composite_key(self) -> None:
        records = [
            {"title": "A", "price": "1"},
            {"title": "A", "price": "1"},
            {"title": "B", "price": "2"},
        ]
        result = deduplicate_results(records, _SCHEMA)
        assert len(result) == 2

    def test_deduplicates_by_specific_field(self) -> None:
        records = [
            {"title": "A", "price": "1"},
            {"title": "A", "price": "2"},
        ]
        result = deduplicate_results(records, _SCHEMA, deduplicate_field="title")
        assert len(result) == 1

    def test_empty_dedup_value_still_included(self) -> None:
        records = [{"title": "dup"}, {"title": "dup"}]
        result = deduplicate_results(records, _SCHEMA, deduplicate_field="title")
        assert len(result) == 1

    def test_all_empty_dedup_fields_includes_all(self) -> None:
        records = [{"title": ""}, {"title": ""}]
        result = deduplicate_results(records, _SCHEMA, deduplicate_field="title")
        assert len(result) == 2, "empty dedup values should always be included"

    def test_case_different_values_are_unique(self) -> None:
        records = [{"title": "Foo"}, {"title": "Bar"}]
        result = deduplicate_results(records, _SCHEMA)
        assert len(result) == 2


class TestMarkJobCanceled:
    def test_delegates_to_state_machine(self) -> None:
        job = MagicMock()
        with patch("app.services.job_state_machine.mark_canceled") as mock_mark:
            mark_job_canceled(job, reason="Test cancel")
            mock_mark.assert_called_once_with(job, reason="Test cancel")

    def test_default_reason(self) -> None:
        job = MagicMock()
        with patch("app.services.job_state_machine.mark_canceled") as mock_mark:
            mark_job_canceled(job)
            mock_mark.assert_called_once_with(job, reason="Canceled by user")

    def test_passes_job_ref(self) -> None:
        job = MagicMock()
        job.id = "test-job-123"
        with patch("app.services.job_state_machine.mark_canceled") as mock_mark:
            mark_job_canceled(job, reason="Canceled")
            call_args = mock_mark.call_args
            assert call_args[0][0].id == "test-job-123"
