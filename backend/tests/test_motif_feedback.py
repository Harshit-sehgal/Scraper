"""Unit tests for motif_feedback — MotifFeedbackEngine and factory function."""

from app.models import FieldType, SchemaField
from app.motif_feedback import MotifFeedbackEngine, get_motif_feedback_engine

# ═══════════════════════════════════════════════════════════════════════════════
# Factory Function
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetMotifFeedbackEngine:
    def test_returns_engine_instance(self) -> None:
        engine = get_motif_feedback_engine()
        assert isinstance(engine, MotifFeedbackEngine)

    def test_returns_new_instance_each_call(self) -> None:
        e1 = get_motif_feedback_engine()
        e2 = get_motif_feedback_engine()
        assert e1 is not e2


# ═══════════════════════════════════════════════════════════════════════════════
# Extract Field Hints from Motifs
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractFieldHintsFromMotifs:
    def test_returns_empty_for_no_motifs(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        hints = MotifFeedbackEngine.extract_field_hints_from_motifs([], schema)
        assert hints == {}

    def test_returns_hint_for_field_in_motif(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        # price appears in 2 motifs, so count >= 2 threshold is met
        motifs: list[tuple[str, ...]] = [("price", "title"), ("price", "availability")]
        hints = MotifFeedbackEngine.extract_field_hints_from_motifs(motifs, schema)
        assert "price" in hints
        assert "HINT" in hints["price"]

    def test_hint_includes_count(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        motifs: list[tuple[str, ...]] = [("price", "title"), ("price", "availability")]
        hints = MotifFeedbackEngine.extract_field_hints_from_motifs(motifs, schema)
        assert "2" in hints["price"]

    def test_skips_fields_not_in_schema(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        motifs: list[tuple[str, ...]] = [("unknown_field", "also_unknown")]
        hints = MotifFeedbackEngine.extract_field_hints_from_motifs(motifs, schema)
        assert hints == {}

    def test_requires_minimum_cooccurrence_for_hint(self) -> None:
        """A field appearing only once (count=1) should not yield a hint (threshold is >=2)."""
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        motifs: list[tuple[str, ...]] = [("price", "title")]
        hints = MotifFeedbackEngine.extract_field_hints_from_motifs(motifs, schema)
        assert hints == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Build Motif Context
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildMotifContext:
    def test_returns_none_for_no_motifs(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        context = MotifFeedbackEngine.build_motif_context([], schema)
        assert context is None

    def test_returns_context_string_with_motifs(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
        ]
        motifs: list[tuple[str, ...]] = [("price", "title")]
        context = MotifFeedbackEngine.build_motif_context(motifs, schema)
        assert context is not None
        assert "LEARNED STRUCTURAL PATTERNS" in context
        assert '"price"' in context
        assert '"title"' in context

    def test_filters_out_unknown_fields(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        motifs: list[tuple[str, ...]] = [("price", "unknown_field")]
        context = MotifFeedbackEngine.build_motif_context(motifs, schema)
        assert context is not None
        assert "unknown_field" not in (context or "")

    def test_returns_none_when_all_fields_filtered(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        motifs: list[tuple[str, ...]] = [("unknown_a", "unknown_b")]
        context = MotifFeedbackEngine.build_motif_context(motifs, schema)
        assert context is None

    def test_limits_to_top_5_motifs(self) -> None:
        schema = [SchemaField(name=f"field{i}", field_type=FieldType.STRING, required=False, description="") for i in range(10)]
        motifs: list[tuple[str, ...]] = [
            ("field0", "field1"),
            ("field2", "field3"),
            ("field4", "field5"),
            ("field6", "field7"),
            ("field8", "field9"),
            ("field0", "field2"),
        ]
        context = MotifFeedbackEngine.build_motif_context(motifs, schema)
        assert context is not None
        # Count motif lines (each starts with "  - ")
        motif_lines = [line for line in context.split("\n") if line.strip().startswith("-")]
        assert len(motif_lines) <= 5

    def test_includes_multiple_fields_in_motif(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
            SchemaField(name="availability", field_type=FieldType.STRING, required=False, description=""),
        ]
        motifs: list[tuple[str, ...]] = [("price", "title", "availability")]
        context = MotifFeedbackEngine.build_motif_context(motifs, schema)
        assert context is not None
        assert '"price"' in context
        assert '"title"' in context
        assert '"availability"' in context


# ═══════════════════════════════════════════════════════════════════════════════
# Extract Motifs from Results
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractMotifsFromResults:
    def test_returns_empty_for_no_results(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        motifs = MotifFeedbackEngine.extract_motifs_from_results([], schema)
        assert motifs == []

    def test_returns_empty_for_single_result_with_one_field(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        results = [{"price": "$100"}]
        motifs = MotifFeedbackEngine.extract_motifs_from_results(results, schema)
        assert motifs == []

    def test_extracts_motif_from_cooccurring_fields(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
        ]
        results = [{"price": "$100", "title": "Widget"}]
        motifs = MotifFeedbackEngine.extract_motifs_from_results(results, schema)
        # Single result: count=1 < min_cooccurrence=2, so no motifs
        assert motifs == []

    def test_extracts_motif_with_sufficient_cooccurrence(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
        ]
        results = [
            {"price": "$100", "title": "Widget"},
            {"price": "$200", "title": "Gadget"},
        ]
        motifs = MotifFeedbackEngine.extract_motifs_from_results(results, schema)
        assert len(motifs) >= 1
        motif_fields = set(motifs[0])
        assert "price" in motif_fields
        assert "title" in motif_fields

    def test_respects_min_cooccurrence(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
        ]
        results = [
            {"price": "$100", "title": "Widget"},
        ]
        motifs = MotifFeedbackEngine.extract_motifs_from_results(results, schema, min_cooccurrence=1)
        assert len(motifs) >= 1

    def test_skips_empty_values(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
        ]
        results = [{"price": "", "title": "Widget"}]
        motifs = MotifFeedbackEngine.extract_motifs_from_results(results, schema)
        assert motifs == []  # price is empty, so only title is present — not enough for a pair

    def test_handles_multiple_motifs(self) -> None:
        schema = [
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
            SchemaField(name="title", field_type=FieldType.STRING, required=False, description=""),
            SchemaField(name="availability", field_type=FieldType.STRING, required=False, description=""),
            SchemaField(name="rating", field_type=FieldType.RATING, required=False, description=""),
        ]
        results = [
            {"price": "$100", "title": "Widget", "availability": "In Stock"},
            {"price": "$200", "title": "Gadget", "availability": "Out of Stock"},
            {"price": "$300", "title": "Thing", "rating": "5 stars"},
            {"price": "$400", "title": "Item", "rating": "4 stars"},
        ]
        motifs = MotifFeedbackEngine.extract_motifs_from_results(results, schema)
        # Should find at least one motif (price+title co-occur in all results)
        assert len(motifs) >= 1
        all_fields: set[str] = set()
        for m in motifs:
            all_fields.update(m)
        assert "price" in all_fields
        assert "title" in all_fields
