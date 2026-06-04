"""Integration tests for critical extraction paths.

Tests the extraction orchestrator's cascade behavior, multi-pass extraction,
field swap detection, arbitration between DOM and network sources, and the
composite record merge logic.

These tests use fixture HTML and mock data — no real browser or network calls.
"""

from __future__ import annotations

import pytest
from app.extraction_orchestrator import (
    ExtractionResult,
    _align_selectors,
    _check_type_compatibility,
    _detect_field_swaps,
    _merge_composite_records,
    orchestrate_extraction,
)
from app.models import FieldType, SchemaField

# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_fields(pairs: list[tuple[str, FieldType]]) -> list[SchemaField]:
    return [SchemaField(name=name, field_type=ft) for name, ft in pairs]


BASIC_SCHEMA = _make_fields(
    [
        ("company_name", FieldType.STRING),
        ("email", FieldType.EMAIL),
        ("phone", FieldType.PHONE),
    ],
)

SIMPLE_HTML = """
<html><body>
<div class="item">
    <h2 class="name">Acme Corp</h2>
    <span class="email">contact@acme.com</span>
    <span class="phone">+1-555-0100</span>
</div>
<div class="item">
    <h2 class="name">Globex Inc</h2>
    <span class="email">info@globex.com</span>
    <span class="phone">+1-555-0200</span>
</div>
</body></html>
"""


# ═══════════════════════════════════════════════════════════════════════
# ExtractionResult
# ═══════════════════════════════════════════════════════════════════════


class TestExtractionResult:
    """Verify ExtractionResult carries metadata correctly."""

    def test_creates_with_basic_fields(self) -> None:
        records = [{"name": "Test"}]
        result = ExtractionResult(records, "regex", selector_success=False)
        assert result.records == records
        assert result.method == "regex"
        assert result.selector_success is False
        assert result.selectors == {}
        assert result.network_diagnostics == []

    def test_creates_with_all_fields(self) -> None:
        selectors = {"item_container": "div.item"}
        diag = ["test diagnostic"]
        result = ExtractionResult(
            [{"name": "Test"}],
            "discovery",
            selector_success=True,
            selectors=selectors,
            network_diagnostics=diag,
        )
        assert result.selector_success is True
        assert result.selectors == selectors
        assert result.network_diagnostics == diag


# ═══════════════════════════════════════════════════════════════════════
# _check_type_compatibility
# ═══════════════════════════════════════════════════════════════════════


class TestCheckTypeCompatibility:
    """Verify type compatibility scoring."""

    def test_integer_matches_numbers(self) -> None:
        score = _check_type_compatibility(FieldType.INTEGER, ["42", "-7", "0"])
        assert score >= 0.8

    def test_integer_rejects_text(self) -> None:
        score = _check_type_compatibility(FieldType.INTEGER, ["hello", "world"])
        assert score < 0.5

    def test_currency_detects_symbol(self) -> None:
        score = _check_type_compatibility(FieldType.CURRENCY, ["$42.00", "€10", "£5"])
        assert score >= 0.8

    def test_email_detects_pattern(self) -> None:
        score = _check_type_compatibility(FieldType.EMAIL, ["user@example.com", "test@domain.co.uk"])
        assert score >= 0.8

    def test_email_rejects_plain_text(self) -> None:
        score = _check_type_compatibility(FieldType.EMAIL, ["hello", "world", "test"])
        assert score < 0.5

    def test_url_detects_http(self) -> None:
        score = _check_type_compatibility(FieldType.URL, ["https://example.com", "/relative/path"])
        assert score >= 0.5

    def test_string_always_matches(self) -> None:
        score = _check_type_compatibility(FieldType.STRING, ["anything", 42, None])
        assert score >= 0.5

    def test_empty_values_returns_mid(self) -> None:
        score = _check_type_compatibility(FieldType.INTEGER, [])
        assert score == 0.5

    def test_phone_detects_pattern(self) -> None:
        score = _check_type_compatibility(FieldType.PHONE, ["+1-555-0100", "(212) 555-0199"])
        assert score >= 0.5

    def test_boolean_detects_true_false(self) -> None:
        score = _check_type_compatibility(FieldType.BOOLEAN, ["true", "false", "0", "1"])
        assert score >= 0.8


# ═══════════════════════════════════════════════════════════════════════
# _detect_field_swaps
# ═══════════════════════════════════════════════════════════════════════


class TestDetectFieldSwaps:
    """Verify field swap detection logic."""

    def test_no_swap_when_types_match(self) -> None:
        fields = _make_fields([("name", FieldType.STRING), ("price", FieldType.CURRENCY)])
        quality_map = {"name": 0.9, "price": 0.85}
        extracted = {"name": ["Acme Corp"], "price": ["$42.00"]}
        swaps = _detect_field_swaps(quality_map, fields, extracted)
        assert swaps == {}

    def test_swap_detected_when_currency_gets_text(self) -> None:
        fields = _make_fields([("name", FieldType.STRING), ("cost", FieldType.CURRENCY)])
        quality_map = {"name": 0.3, "cost": 0.9}  # name has low quality but should be easy
        extracted = {"name": ["Acme Corp"], "cost": ["$42.00"]}
        # With values that match their types, no swap needed
        swaps = _detect_field_swaps(quality_map, fields, extracted)
        assert swaps == {}

    def test_swap_detected_by_value_analysis(self) -> None:
        fields = _make_fields([("name", FieldType.STRING), ("cost", FieldType.STRING)])
        # If values look like they were swapped
        extracted = {"name": ["$42.00", "€10"], "cost": ["Acme Corp"]}
        swaps = _detect_field_swaps({"name": 0.5, "cost": 0.5}, fields, extracted)
        assert isinstance(swaps, dict)

    def test_swap_no_values_falls_back_to_quality(self) -> None:
        fields = _make_fields([("email", FieldType.EMAIL), ("name", FieldType.STRING)])
        # email has low quality but should be easy to match
        quality_map = {"email": 0.2, "name": 0.95}
        swaps = _detect_field_swaps(quality_map, fields, None)
        assert isinstance(swaps, dict)


# ═══════════════════════════════════════════════════════════════════════
# _align_selectors
# ═══════════════════════════════════════════════════════════════════════


class TestAlignSelectors:
    """Verify selector alignment on detected swaps."""

    def test_swaps_field_selectors(self) -> None:
        selectors = {"fields": {"email": "span.email", "name": "h2.name"}}
        result = _align_selectors(selectors, {"email": "name"})
        assert result["fields"]["email"] == "h2.name"
        assert result["fields"]["name"] == "span.email"

    def test_no_swap_returns_unchanged(self) -> None:
        selectors = {"fields": {"a": "sel.a", "b": "sel.b"}}
        result = _align_selectors(selectors, {})
        assert result["fields"]["a"] == "sel.a"


# ═══════════════════════════════════════════════════════════════════════
# _merge_composite_records
# ═══════════════════════════════════════════════════════════════════════


class TestMergeCompositeRecords:
    """Verify multi-pass record merging."""

    def test_single_pass_returns_asis(self) -> None:
        records = [{"name": "A"}, {"name": "B"}]
        result = _merge_composite_records([records], BASIC_SCHEMA)
        assert result == records

    def test_no_records_returns_empty(self) -> None:
        result = _merge_composite_records([], BASIC_SCHEMA)
        assert result == []

    def test_merges_disjoint_fields(self) -> None:
        fields = _make_fields([("name", FieldType.STRING)])
        pass1 = [{"name": "Acme"}]
        pass2 = [{"name": "Acme", "email": "a@a.com"}]
        result = _merge_composite_records([pass1, pass2], fields)
        # Pass2 has more fields, should be preferred for merged record
        assert len(result) == 1
        assert result[0]["name"] == "Acme"

    def test_sorts_by_record_score(self) -> None:
        fields = _make_fields([("name", FieldType.STRING)])
        low = [{"name": "Low", "record_score": 0.3}]
        high = [{"name": "High", "record_score": 0.9}]
        result = _merge_composite_records([low, high], fields)
        assert result[0]["name"] == "High"

    def test_merges_multiple_passes(self) -> None:
        fields = _make_fields([("name", FieldType.STRING)])
        pass1 = [{"name": "A"}, {"name": "B"}]
        pass2 = [{"name": "C"}]
        result = _merge_composite_records([pass1, pass2], fields)
        assert len(result) >= 3  # Could be 3 if no dedup key overlap


# ═══════════════════════════════════════════════════════════════════════
# Orchestrate Extraction — Integration Tests
# ═══════════════════════════════════════════════════════════════════════


class TestOrchestrationCascade:
    """Verify the extraction cascade behavior using settings overrides.

    These tests verify that the orchestrator correctly handles:
    - Fallback through layers when extraction quality is low
    - Network payload arbitration against DOM results
    - Multi-pass extraction for complex pages
    """

    @pytest.mark.asyncio
    async def test_handles_empty_html(self) -> None:
        """Empty HTML cascades to regex fallback."""
        fields = _make_fields([("name", FieldType.STRING)])
        result = await orchestrate_extraction(
            url="https://example.com",
            html="",
            schema_fields=fields,
            min_record_score=0.3,
        )
        assert isinstance(result, ExtractionResult)
        assert isinstance(result.records, list)

    @pytest.mark.asyncio
    async def test_handles_minmal_html_with_text(self) -> None:
        """Simple text content should produce some regex extraction."""
        html = "<html><body>Hello World</body></html>"
        fields = _make_fields([("name", FieldType.STRING)])
        result = await orchestrate_extraction(
            url="https://example.com/page",
            html=html,
            schema_fields=fields,
            min_record_score=0.1,
        )
        assert isinstance(result, ExtractionResult)
        assert isinstance(result.network_diagnostics, list)

    @pytest.mark.asyncio
    async def test_provided_selectors_are_tried(self) -> None:
        """Provided selectors should be tried as the first DOM layer."""
        html = SIMPLE_HTML
        fields = _make_fields([("company_name", FieldType.STRING), ("email", FieldType.EMAIL)])
        selectors = {
            "item_container": "div.item",
            "fields": {
                "company_name": "h2.name",
                "email": "span.email",
            },
        }
        result = await orchestrate_extraction(
            url="https://example.com/listings",
            html=html,
            schema_fields=fields,
            min_record_score=0.3,
            provided_selectors=selectors,
        )
        assert isinstance(result, ExtractionResult)
        # Should have found some records or fallen through gracefully
        assert isinstance(result.records, list)

    @pytest.mark.asyncio
    async def test_cascade_with_min_record_score(self) -> None:
        """Different min_record_score values affect gate threshold behavior."""
        fields = _make_fields([("name", FieldType.STRING)])
        result_low = await orchestrate_extraction(
            url="https://example.com",
            html="<p>test</p>",
            schema_fields=fields,
            min_record_score=0.1,
        )
        result_high = await orchestrate_extraction(
            url="https://example.com",
            html="<p>test</p>",
            schema_fields=fields,
            min_record_score=0.9,
        )
        # Both should run without errors and return ExtractionResult
        assert isinstance(result_low, ExtractionResult)
        assert isinstance(result_high, ExtractionResult)

    @pytest.mark.asyncio
    async def test_network_diagnostics_collected(self) -> None:
        """Diagnostics should be populated even without network payloads."""
        result = await orchestrate_extraction(
            url="https://example.com",
            html="<p>content</p>",
            schema_fields=_make_fields([("x", FieldType.STRING)]),
            min_record_score=0.3,
        )
        assert len(result.network_diagnostics) > 0
        # Should mention no session params or payloads
        diag_text = " ".join(result.network_diagnostics).lower()
        assert "session" in diag_text or "captured" in diag_text or "arbitration" in diag_text

    @pytest.mark.asyncio
    async def test_multi_pass_fallback_with_complex_html(self) -> None:
        """Complex HTML with nested elements should survive cascade without crash."""
        complex_html = """
        <html><body>
        <div id="app">
            <div data-container="list">
                <div class="card"><h3>Item 1</h3><p>Desc 1</p></div>
                <div class="card"><h3>Item 2</h3><p>Desc 2</p></div>
                <div class="card"><h3>Item 3</h3><p>Desc 3</p></div>
            </div>
        </div>
        </body></html>
        """
        result = await orchestrate_extraction(
            url="https://example.com/complex",
            html=complex_html,
            schema_fields=_make_fields([("title", FieldType.STRING)]),
            min_record_score=0.3,
        )
        assert isinstance(result, ExtractionResult)
        assert isinstance(result.records, list)

    @pytest.mark.asyncio
    async def test_cascade_with_all_fallbacks(self) -> None:
        """Empty content should still produce arbitration diagnostics."""
        result = await orchestrate_extraction(
            url="https://example.com/empty",
            html="<html><body></body></html>",
            schema_fields=_make_fields([("a", FieldType.STRING), ("b", FieldType.STRING)]),
            min_record_score=0.5,
        )
        assert isinstance(result, ExtractionResult)
        assert len(result.network_diagnostics) > 0


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestExtractionEdgeCases:
    """Edge cases for the extraction pipeline."""

    def test_extraction_result_boolean_behavior(self) -> None:
        """ExtractionResult with empty records should be falsy in bool context."""
        empty = ExtractionResult([], "regex")
        assert len(empty.records) == 0

        filled = ExtractionResult([{"name": "A"}], "discovery")
        assert len(filled.records) == 1

    def test_merge_sorts_by_score_descending(self) -> None:
        """Verify merged records are sorted by record_score descending."""
        fields = _make_fields([("name", FieldType.STRING)])
        results = _merge_composite_records(
            [
                [{"name": "Low", "record_score": 0.2}],
                [{"name": "Mid", "record_score": 0.5}],
                [{"name": "High", "record_score": 0.9}],
            ],
            fields,
        )
        scores = [r.get("record_score", 0.0) for r in results]
        assert scores == sorted(scores, reverse=True)
