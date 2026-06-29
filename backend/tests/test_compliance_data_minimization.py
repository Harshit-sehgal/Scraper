"""Comp 6: Data minimization enforcement — test that only requested fields are extracted."""
from __future__ import annotations


def _minimize_results(
    raw_results: list[dict],
    requested_fields: set[str],
) -> list[dict]:
    """Strip any fields not in the requested set from results."""
    minimized = []
    for record in raw_results:
        minimized.append({k: v for k, v in record.items() if k in requested_fields or k.startswith("_")})
    return minimized


class TestDataMinimization:
    def test_only_requested_fields_kept(self) -> None:
        records = [{"name": "Product", "price": "$10", "internal_id": "abc123", "secret_note": "confidential"}]
        minimized = _minimize_results(records, {"name", "price"})
        assert "name" in minimized[0]
        assert "price" in minimized[0]
        assert "internal_id" not in minimized[0]
        assert "secret_note" not in minimized[0]

    def test_system_fields_preserved(self) -> None:
        records = [{"title": "A", "_record_id": "rec-1", "_provenance": "regex", "extra": "x"}]
        minimized = _minimize_results(records, {"title"})
        assert "_record_id" in minimized[0]
        assert "_provenance" in minimized[0]
        assert "extra" not in minimized[0]

    def test_empty_field_set_returns_only_system(self) -> None:
        records = [{"a": 1, "b": 2, "_meta": "sys"}]
        minimized = _minimize_results(records, set())
        assert minimized[0] == {"_meta": "sys"}

    def test_all_fields_requested(self) -> None:
        records = [{"a": 1, "b": 2, "c": 3}]
        minimized = _minimize_results(records, {"a", "b", "c"})
        assert minimized[0] == records[0]

    def test_none_values_handled(self) -> None:
        records = [{"name": None, "price": None}]
        minimized = _minimize_results(records, {"name"})
        assert "name" in minimized[0]
        assert minimized[0]["name"] is None

    def test_empty_results(self) -> None:
        minimized = _minimize_results([], {"x"})
        assert minimized == []

    def test_extra_field_not_in_schema_removed(self) -> None:
        records = [{"title": "Widget", "description": "A widget", "hidden_field": "should_not_appear"}]
        minimized = _minimize_results(records, {"title", "description"})
        assert "hidden_field" not in minimized[0]
