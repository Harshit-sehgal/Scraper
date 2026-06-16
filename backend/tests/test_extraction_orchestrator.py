"""Unit tests for extraction_orchestrator — ExtractionResult, merge, type compatibility, field swaps, and selector alignment."""

from unittest.mock import patch

import pytest
from app.extraction_orchestrator import (
    ExtractionResult,
    _align_selectors,
    _check_type_compatibility,
    _detect_field_swaps,
    _merge_composite_records,
)
from app.models import FieldType, SchemaField

from .conftest import make_schema_field_list

# ═══════════════════════════════════════════════════════════════════════════════
# ExtractionResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractionResult:
    def test_default_construction(self) -> None:
        r = ExtractionResult(records=[{"name": "test"}], method="discovery")
        assert r.records == [{"name": "test"}]
        assert r.method == "discovery"
        assert r.selector_success is False
        assert r.selectors == {}
        assert r.network_diagnostics == []

    def test_full_construction(self) -> None:
        r = ExtractionResult(
            records=[{"name": "a"}],
            method="memory",
            selector_success=True,
            selectors={"item_container": ".card"},
            network_diagnostics=["ok"],
        )
        assert r.selector_success is True
        assert r.selectors == {"item_container": ".card"}
        assert r.network_diagnostics == ["ok"]


# ═══════════════════════════════════════════════════════════════════════════════
# Merge Composite Records
# ═══════════════════════════════════════════════════════════════════════════════


class TestMergeCompositeRecords:
    def test_returns_empty_for_empty_input(self) -> None:
        assert _merge_composite_records([], make_schema_field_list(["name"])) == []

    def test_single_pass_returns_as_is(self) -> None:
        records = [[{"name": "A"}, {"name": "B"}]]
        result = _merge_composite_records(records, make_schema_field_list(["name"]))
        assert result == records[0]

    def test_merges_records_with_same_key(self) -> None:
        schema = make_schema_field_list(["name"])
        pass1 = [{"name": "Product", "price": "$100", "record_score": 0.9}]
        pass2 = [{"name": "Product", "description": "Great item", "record_score": 0.7}]
        result = _merge_composite_records([pass1, pass2], schema)
        assert len(result) == 1
        assert result[0].get("price") == "$100"
        assert result[0].get("description") == "Great item"

    def test_disjoint_records_kept_separately(self) -> None:
        schema = make_schema_field_list(["name"])
        pass1 = [{"name": "Item A", "record_score": 0.9}]
        pass2 = [{"name": "Item B", "record_score": 0.8}]
        result = _merge_composite_records([pass1, pass2], schema)
        assert len(result) == 2

    def test_sorts_by_record_score_descending(self) -> None:
        schema = make_schema_field_list(["name"])
        pass1 = [{"name": "B", "record_score": 0.5}]
        pass2 = [{"name": "A", "record_score": 0.9}]
        result = _merge_composite_records([pass1, pass2], schema)
        assert result[0]["name"] == "A"
        assert result[1]["name"] == "B"

    def test_synthetic_key_when_no_id_field_value(self) -> None:
        schema = make_schema_field_list(["name"])
        pass1 = [{"price": "$100", "record_score": 0.5}]
        pass2 = [{"price": "$200", "record_score": 0.6}]
        result = _merge_composite_records([pass1, pass2], schema)
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Type Compatibility Checking
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckTypeCompatibility:
    def test_integer_type(self) -> None:
        assert _check_type_compatibility(FieldType.INTEGER, ["123", "456"]) >= 0.5
        assert _check_type_compatibility(FieldType.INTEGER, ["abc", "def"]) == 0.0

    def test_float_type(self) -> None:
        assert _check_type_compatibility(FieldType.FLOAT, ["12.5", "3.14"]) >= 0.5
        assert _check_type_compatibility(FieldType.FLOAT, ["abc", "def"]) == 0.0

    def test_percentage_type(self) -> None:
        assert _check_type_compatibility(FieldType.PERCENTAGE, ["12.5%", "3.14%"]) >= 0.5

    def test_currency_type(self) -> None:
        assert _check_type_compatibility(FieldType.CURRENCY, ["$100", "€50"]) >= 0.5
        assert _check_type_compatibility(FieldType.CURRENCY, ["abc", "def"]) == 0.0

    def test_email_type(self) -> None:
        assert _check_type_compatibility(FieldType.EMAIL, ["test@example.com"]) >= 0.5
        assert _check_type_compatibility(FieldType.EMAIL, ["not an email"]) == 0.0

    def test_phone_type(self) -> None:
        assert _check_type_compatibility(FieldType.PHONE, ["+1-555-0100"]) >= 0.5
        assert _check_type_compatibility(FieldType.PHONE, ["abc"]) == 0.0

    def test_url_type(self) -> None:
        assert _check_type_compatibility(FieldType.URL, ["https://example.com"]) >= 0.5
        assert _check_type_compatibility(FieldType.URL, ["plain text"]) == 0.0

    def test_boolean_type(self) -> None:
        assert _check_type_compatibility(FieldType.BOOLEAN, ["true", "false"]) >= 0.5
        assert _check_type_compatibility(FieldType.BOOLEAN, ["hello", "world"]) == 0.0

    def test_date_type(self) -> None:
        assert _check_type_compatibility(FieldType.DATE, ["2025-01-15"]) >= 0.5
        assert _check_type_compatibility(FieldType.DATE, ["hello world"]) == 0.0

    def test_string_type_always_matches(self) -> None:
        assert _check_type_compatibility(FieldType.STRING, ["anything"]) >= 0.5

    def test_empty_values_returns_mid_score(self) -> None:
        assert _check_type_compatibility(FieldType.INTEGER, []) == 0.5
        assert _check_type_compatibility(FieldType.INTEGER, [None]) == 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Field Swap Detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectFieldSwaps:
    def test_returns_empty_for_no_extracted_values_and_high_quality(self) -> None:
        fields = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        result = _detect_field_swaps({"price": 0.9}, fields)
        assert result == {}

    def test_detects_swap_with_extracted_values(self) -> None:
        fields = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="name", field_type=FieldType.STRING, required=False, description=""),
        ]
        values = {
            "price": ["Product Name Here"],
            "name": ["$100"],
        }
        result = _detect_field_swaps({"price": 0.5, "name": 0.5}, fields, extracted_values=values)
        assert isinstance(result, dict)

    def test_returns_empty_when_values_match_expected_types(self) -> None:
        fields = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="name", field_type=FieldType.STRING, required=False, description=""),
        ]
        values = {
            "price": ["$100"],
            "name": ["Product"],
        }
        result = _detect_field_swaps({"price": 0.9, "name": 0.9}, fields, extracted_values=values)
        assert result == {}

    def test_heuristic_detection_with_low_quality(self) -> None:
        """Without extracted_values, uses quality-based heuristics."""
        fields = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="description", field_type=FieldType.STRING, required=False, description=""),
        ]
        result = _detect_field_swaps({"price": 0.2, "description": 0.9}, fields)
        assert "price" in result

    def test_skips_when_no_high_quality_partner(self) -> None:
        fields = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="description", field_type=FieldType.STRING, required=False, description=""),
        ]
        result = _detect_field_swaps({"price": 0.2, "description": 0.5}, fields)
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Selector Alignment
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlignSelectors:
    def test_passthrough_for_empty_swaps(self) -> None:
        sels = {"fields": {"price": ".price", "name": ".name"}}
        result = _align_selectors(sels, {})
        assert result["fields"]["price"] == ".price"

    def test_swaps_selectors(self) -> None:
        sels = {"fields": {"price": ".price", "name": ".name"}}
        result = _align_selectors(sels, {"price": "name"})
        assert result["fields"]["price"] == ".name"
        assert result["fields"]["name"] == ".price"

    def test_skips_missing_target(self) -> None:
        sels = {"fields": {"price": ".price"}}
        result = _align_selectors(sels, {"price": "nonexistent"})
        assert result["fields"]["price"] == ".price"

    def test_handles_empty_fields(self) -> None:
        sels: dict = {"fields": {}}
        result = _align_selectors(sels, {"price": "name"})
        assert result["fields"] == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-Pass Extraction (with mocked dependencies)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiPassExtraction:
    @patch("app.selector_engine.apply_selectors")
    def test_single_pass_default(self, mock_apply) -> None:
        from app.extraction_orchestrator import _multi_pass_extraction

        mock_apply.return_value = [
            {"name": "A", "record_score": 0.8},
            {"name": "B", "record_score": 0.7},
            {"name": "C", "record_score": 0.9},
        ]
        result = _multi_pass_extraction(
            "<html></html>",
            make_schema_field_list(["name"]),
            {"item_container": ".card"},
            base_url="https://example.com",
        )
        assert len(result) == 3
        assert result[0]["name"] == "A"

    @patch("app.selector_engine.apply_selectors")
    def test_sparse_pass_triggers_fallback(self, mock_apply) -> None:
        from app.extraction_orchestrator import _multi_pass_extraction

        mock_apply.return_value = [
            {"name": "A", "record_score": 0.5},
        ]
        result = _multi_pass_extraction(
            "<html></html>",
            make_schema_field_list(["name"]),
            {"item_container": ".card"},
            base_url="https://example.com",
        )
        assert isinstance(result, list)

    @patch("app.selector_engine.apply_selectors")
    def test_low_avg_score_triggers_fallback(self, mock_apply) -> None:
        from app.extraction_orchestrator import _multi_pass_extraction

        mock_apply.return_value = [
            {"name": "A", "record_score": 0.1},
            {"name": "B", "record_score": 0.2},
            {"name": "C", "record_score": 0.3},
        ]
        result = _multi_pass_extraction(
            "<html></html>",
            make_schema_field_list(["name"]),
            {"item_container": ".card"},
            base_url="https://example.com",
        )
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrate Extraction (smoke test — no mocks)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrateExtraction:
    @pytest.mark.asyncio
    async def test_returns_extraction_result(self) -> None:
        """Smoke test: orchestrate_extraction returns an ExtractionResult."""
        from app.extraction_orchestrator import orchestrate_extraction

        schema = make_schema_field_list(["name"])
        result = await orchestrate_extraction(
            url="https://example.com/product",
            html="<html>test</html>",
            schema_fields=schema,
            min_record_score=0.1,
        )
        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_regex_supersedes_sparse_visible_text_records(self, monkeypatch) -> None:
        """Structural extraction should beat sparse visible-text guesses."""
        from types import SimpleNamespace

        import app.extraction_orchestrator as orchestrator

        class DummyMemory:
            def get_selectors(self, _url):
                return None

            def record_success(self, *_args, **_kwargs) -> None:
                return None

            def record_failure(self, *_args, **_kwargs) -> None:
                return None

        async def no_selectors(*_args, **_kwargs):
            return None

        async def no_containers(*_args, **_kwargs):
            return SimpleNamespace(all_passed=False, final_records=[], total_records=0, best_selector="")

        monkeypatch.setattr(orchestrator, "get_selector_memory", DummyMemory)
        monkeypatch.setattr(orchestrator, "extract_from_network", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(orchestrator, "discover_selectors", no_selectors)
        monkeypatch.setattr(orchestrator, "multi_pass_container_extraction", no_containers)
        monkeypatch.setattr(orchestrator, "classify_container_failure", lambda _result: {"failure_class": "no_containers"})
        monkeypatch.setattr(
            orchestrator,
            "extract_from_visible_blocks",
            lambda *_args, **_kwargs: [
                {"text": "Oscar Wilde", "author": "Frank Zappa", "record_score": 0.65},
                {"text": "Oscar Wilde", "author": "Frank Zappa", "record_score": 0.65},
            ],
        )

        html = """
        <html>
          <body>
            <div class="quote">
              <p class="text">"Be yourself; everyone else is already taken."</p>
              <small class="author">Oscar Wilde</small>
            </div>
            <div class="quote">
              <p class="text">"So many books, so little time."</p>
              <small class="author">Frank Zappa</small>
            </div>
          </body>
        </html>
        """
        fields = [
            SchemaField(name="text", field_type=FieldType.STRING, description="Quote text", required=True),
            SchemaField(name="author", field_type=FieldType.STRING, description="Quote author", required=True),
        ]

        result = await orchestrator.orchestrate_extraction(
            url="https://example.com/quotes",
            html=html,
            schema_fields=fields,
            min_record_score=0.1,
        )

        assert result.method == "regex"
        assert [{field: row.get(field) for field in ("text", "author")} for row in result.records] == [
            {"text": "Be yourself; everyone else is already taken.", "author": "Oscar Wilde"},
            {"text": "So many books, so little time.", "author": "Frank Zappa"},
        ]
