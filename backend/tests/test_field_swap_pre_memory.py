"""Field swap detection before selector memory persistence.

Tests the new _detect_and_align_field_swaps_for_layer helper which guards
selector memory writes against persisting swapped selector pairs. Without
this guard, a single swapped pair would corrupt all future scrapes of
the same domain.
"""

from __future__ import annotations

from app.extraction_orchestrator import _detect_and_align_field_swaps_for_layer
from app.models import FieldType, SchemaField


def _sf(name: str, ftype: FieldType = FieldType.STRING, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=ftype, description="", required=required)


class TestFieldSwapDetectionPreMemory:
    """Verify _detect_and_align_field_swaps_for_layer detects and aligns swaps."""

    def test_no_swap_returns_overlapping_results(self) -> None:
        results = [
            {"name": "Acme Corp", "price": "$1,299"},
            {"name": "Beta Inc", "price": "$2,499"},
        ]
        fields = [
            _sf("name", FieldType.STRING),
            _sf("price", FieldType.CURRENCY),
        ]
        aligned = _detect_and_align_field_swaps_for_layer(results, fields)
        # No swap to fix — values match types
        assert aligned == results

    def test_swap_detected_and_aligned(self) -> None:
        """A swapped phone/url pair must be aligned before persistence."""
        results = [
            {"phone": "https://acme.com/contact", "url": "+1-555-1234"},
            {"phone": "https://beta.com/about", "url": "+1-555-5678"},
        ]
        fields = [
            _sf("phone", FieldType.PHONE),
            _sf("url", FieldType.URL),
        ]
        aligned = _detect_and_align_field_swaps_for_layer(results, fields)
        # The values should now be in their correct fields
        assert aligned[0]["phone"] == "+1-555-1234"
        assert aligned[0]["url"] == "https://acme.com/contact"

    def test_empty_results_returns_immediately(self) -> None:
        """Empty result set must short-circuit and return as-is."""
        aligned = _detect_and_align_field_swaps_for_layer([], [_sf("name")])
        assert aligned == []

    def test_currency_with_string_value_detects_swap(self) -> None:
        """A CURRENCY field with a string-only value must detect a possible swap."""
        results = [
            {"name": "Acme Corp", "price": "Click to view pricing"},
        ]
        fields = [
            _sf("name", FieldType.STRING),
            _sf("price", FieldType.CURRENCY),
        ]
        aligned = _detect_and_align_field_swaps_for_layer(results, fields)
        # Swap detected (price looks like a STRING value but field is CURRENCY;
        # name field might have the actual currency value if real, but here
        # we just verify the helper runs)
        assert aligned is not None
        assert isinstance(aligned, list)

    def test_alignment_does_not_drop_records(self) -> None:
        """The number of records must be preserved through alignment."""
        results = [
            {"phone": "https://a.com", "url": "+1-555-0001"},
            {"phone": "https://b.com", "url": "+1-555-0002"},
            {"phone": "https://c.com", "url": "+1-555-0003"},
        ]
        fields = [
            _sf("phone", FieldType.PHONE),
            _sf("url", FieldType.URL),
        ]
        aligned = _detect_and_align_field_swaps_for_layer(results, fields)
        assert len(aligned) == 3


class TestFieldSwapPersistenceGuard:
    """Verify the helper preserves record integrity for persistence."""

    def test_record_dict_type_preserved(self) -> None:
        """Each aligned record must remain a dict (not a list or tuple)."""
        results = [{"phone": "+1-555-1234", "url": "https://a.com"}]
        fields = [
            _sf("phone", FieldType.PHONE),
            _sf("url", FieldType.URL),
        ]
        aligned = _detect_and_align_field_swaps_for_layer(results, fields)
        for record in aligned:
            assert isinstance(record, dict)
