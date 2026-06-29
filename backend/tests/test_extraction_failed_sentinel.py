"""Tests for _ExtractionFailedSentinel in pagination_executor.

Regression tests pinning the singleton sentinel pattern that replaced the
old dict-based ``{"_extraction_failed": "true"}`` marker. The old approach
had two failure modes:

1. ``rec is _EXTRACTION_FAILED_MARKER`` — breaks if anyone copies the dict.
2. ``rec.get("_extraction_failed") == "true"`` — breaks if value type
   changes silently (e.g., ``True`` bool vs ``"true"`` string).

The sentinel class + isinstance check eliminates both.
"""

from __future__ import annotations

from typing import Any

from app.pagination_executor import (
    _EXTRACTION_FAILED_MARKER,
    PaginationResult,
    _extract_marker_and_count,
    _ExtractionFailedSentinel,
)


class TestExtractionFailedSentinel:
    def test_singleton_identity(self) -> None:
        """Two calls to the constructor return the exact same object."""
        a = _ExtractionFailedSentinel()
        b = _ExtractionFailedSentinel()
        assert a is b

    def test_marker_is_singleton(self) -> None:
        """Module-level marker is the same instance as a fresh call."""
        assert _EXTRACTION_FAILED_MARKER is _ExtractionFailedSentinel()

    def test_isinstance_check_works(self) -> None:
        """isinstance correctly identifies the sentinel."""
        assert isinstance(_EXTRACTION_FAILED_MARKER, _ExtractionFailedSentinel)

    def test_isinstance_rejects_dict(self) -> None:
        """A regular dict is NOT misidentified as a sentinel."""
        assert not isinstance({"_extraction_failed": "true"}, _ExtractionFailedSentinel)


class TestExtractMarkerAndCount:
    def test_strips_sentinel_and_increments_failures(self) -> None:
        """Sentinel records are stripped and counted, real records kept."""
        records: list[dict[str, Any] | _ExtractionFailedSentinel] = [
            {"name": "Product A", "price": "$10"},
            _EXTRACTION_FAILED_MARKER,
            {"name": "Product B", "price": "$20"},
        ]
        result = PaginationResult()
        clean = _extract_marker_and_count(records, result)
        assert len(clean) == 2
        assert clean[0]["name"] == "Product A"
        assert clean[1]["name"] == "Product B"
        assert result.extraction_failures == 1

    def test_multiple_sentinels_counted(self) -> None:
        """Multiple sentinel records each increment the failure counter."""
        records: list[dict[str, Any] | _ExtractionFailedSentinel] = [
            _EXTRACTION_FAILED_MARKER,
            _EXTRACTION_FAILED_MARKER,
            {"name": "A"},
        ]
        result = PaginationResult()
        clean = _extract_marker_and_count(records, result)
        assert len(clean) == 1
        assert result.extraction_failures == 2

    def test_no_sentinels_means_zero_failures(self) -> None:
        """Clean records produce zero failures."""
        records = [{"name": "A"}, {"name": "B"}]
        result = PaginationResult()
        clean = _extract_marker_and_count(records, result)
        assert len(clean) == 2
        assert result.extraction_failures == 0

    def test_empty_list_returns_empty(self) -> None:
        """Empty input is handled gracefully."""
        result = PaginationResult()
        clean = _extract_marker_and_count([], result)
        assert clean == []
        assert result.extraction_failures == 0

    def test_old_dict_marker_not_treated_as_sentinel(self) -> None:
        """Legacy dict-based marker is NOT treated as a failure sentinel.

        This pins the fix: the old ``{"_extraction_failed": "true"}`` dict
        must pass through as a regular record, since the sentinel class
        replaced the dict-based approach.
        """
        old_marker = {"_extraction_failed": "true"}
        records = [old_marker, {"name": "Real Record"}]
        result = PaginationResult()
        clean = _extract_marker_and_count(records, result)
        assert len(clean) == 2
        assert result.extraction_failures == 0
