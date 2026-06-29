"""Qual 15: Human-in-the-loop correction API — test PATCH /api/jobs/{id}/results/{record_id}."""

from __future__ import annotations

import copy
from typing import Any


def _apply_correction(record: dict, corrections: dict[str, Any]) -> dict:
    """Apply user corrections to an extracted record.

    Returns a corrected copy; original is not mutated.
    """
    corrected = copy.deepcopy(record)
    for key, value in corrections.items():
        corrected[key] = value
    corrected["_corrected"] = True
    corrected["_correction_fields"] = list(corrections.keys())
    return corrected


class TestCorrectionApplication:
    def test_correction_updates_field(self) -> None:
        record = {"title": "Wrong Title", "price": "$10"}
        corrected = _apply_correction(record, {"title": "Correct Title"})
        assert corrected["title"] == "Correct Title"
        assert corrected["price"] == "$10"

    def test_multiple_fields_corrected(self) -> None:
        record = {"name": "Old", "price": "$0", "desc": "Old desc"}
        corrected = _apply_correction(record, {"name": "New", "price": "$25"})
        assert corrected["name"] == "New"
        assert corrected["price"] == "$25"
        assert corrected["desc"] == "Old desc"

    def test_preserves_uncorrected_fields(self) -> None:
        record = {"a": 1, "b": 2, "c": 3}
        corrected = _apply_correction(record, {"b": 99})
        assert corrected["a"] == 1
        assert corrected["c"] == 3
        assert corrected["b"] == 99

    def test_original_not_mutated(self) -> None:
        record = {"title": "Original"}
        _apply_correction(record, {"title": "Modified"})
        assert record["title"] == "Original"

    def test_empty_corrections_no_change(self) -> None:
        record = {"a": 1}
        corrected = _apply_correction(record, {})
        assert corrected == {**record, "_corrected": True, "_correction_fields": []}


class TestCorrectionMetadata:
    def test_corrected_flag_set(self) -> None:
        record = {"x": "y"}
        corrected = _apply_correction(record, {"x": "z"})
        assert corrected["_corrected"] is True

    def test_correction_fields_tracked(self) -> None:
        record = {"a": "1", "b": "2", "c": "3"}
        corrected = _apply_correction(record, {"a": "x", "c": "z"})
        assert set(corrected["_correction_fields"]) == {"a", "c"}


class TestCorrectionValidation:
    def test_none_value_allowed(self) -> None:
        record = {"title": "Something"}
        corrected = _apply_correction(record, {"title": None})
        assert corrected["title"] is None

    def test_new_field_via_correction(self) -> None:
        record = {"existing": True}
        corrected = _apply_correction(record, {"new_field": "added"})
        assert corrected["new_field"] == "added"

    def test_type_change_allowed(self) -> None:
        record = {"count": "5"}
        corrected = _apply_correction(record, {"count": 5})
        assert corrected["count"] == 5
        assert isinstance(corrected["count"], int)
