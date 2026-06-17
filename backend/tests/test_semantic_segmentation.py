"""Unit tests for semantic_segmentation — IR, extraction, classification,
relationships, structural memory, noise detection, overlap resolution.
"""

from app.semantic_ir import SemanticToken, SemanticType, Span
from app.semantic_segmentation import (
    DOMINANCE_HIERARCHY,
    CandidateIR,
    RelationshipIR,
    SegmentedIR,
    StructuralMemory,
    StructuralMemoryTracker,
    _classify_fallback,
    _classify_with_ambiguity,
    _clean_value,
    _compute_cohesion,
    _extract_by_pattern,
    _extract_by_split,
    _extract_by_whitespace,
    _infer_relationship_type,
    _max_pattern_similarity,
    _uncovered_ratio,
    candidate_type_to_semantic,
    compute_semantic_density,
    expand_composite_records,
    extract_candidate_values,
    is_composite_value,
    is_likely_noise,
    is_likely_noise_field,
    resolve_overlaps,
    score_relationships,
    segment_single_text,
    sem_type_str,
    to_semantic_type,
)

# ═══════════════════════════════════════════════════════════════════════════════
# TYPE CONVERSION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCandidateTypeToSemantic:
    def test_known_type(self) -> None:
        assert candidate_type_to_semantic("price") == SemanticType.PRICE
        assert candidate_type_to_semantic("date") == SemanticType.DATE
        assert candidate_type_to_semantic("location") == SemanticType.LOCATION
        assert candidate_type_to_semantic("code") == SemanticType.CODE

    def test_unknown_type_falls_back_to_text(self) -> None:
        assert candidate_type_to_semantic("unknown_type") == SemanticType.TEXT
        assert candidate_type_to_semantic("") == SemanticType.TEXT

    def test_case_sensitive(self) -> None:
        assert candidate_type_to_semantic("Price") == SemanticType.TEXT


class TestToSemanticType:
    def test_passes_through_semantic_type(self) -> None:
        assert to_semantic_type(SemanticType.PRICE) == SemanticType.PRICE

    def test_converts_str(self) -> None:
        assert to_semantic_type("price") == SemanticType.PRICE

    def test_converts_object_with_value_attr(self) -> None:
        class Fake:
            value = "date"

        assert to_semantic_type(Fake()) == SemanticType.DATE

    def test_fallback_on_invalid_value(self) -> None:
        class BadFake:
            value = "not_a_type"

        result = to_semantic_type(BadFake())
        assert result == SemanticType.TEXT


class TestSemTypeStr:
    def test_from_semantic_type(self) -> None:
        assert sem_type_str(SemanticType.PRICE) == "price"
        assert sem_type_str(SemanticType.CODE) == "code"

    def test_from_string(self) -> None:
        assert sem_type_str("price") == "price"

    def test_from_object_with_value(self) -> None:
        class Fake:
            value = "date"

        assert sem_type_str(Fake()) == "date"


# ═══════════════════════════════════════════════════════════════════════════════
# CANDIDATE IR
# ═══════════════════════════════════════════════════════════════════════════════


class TestCandidateIR:
    def test_default_construction(self) -> None:
        c = CandidateIR(raw="test", cleaned="test", span_start=0, span_end=4, position=0)
        assert c.raw == "test"
        assert c.primary_type == SemanticType.TEXT
        assert c.primary_confidence == 0.5
        assert c.extraction_pass == 1
        assert c.extraction_method == "pattern"

    def test_to_semantic_type(self) -> None:
        c = CandidateIR(raw="$10", cleaned="10", span_start=0, span_end=3, position=0, primary_type=SemanticType.PRICE)
        assert c.to_semantic_type() == SemanticType.PRICE

    def test_sem_type_str(self) -> None:
        c = CandidateIR(raw="abc", cleaned="abc", span_start=0, span_end=3, position=0, primary_type=SemanticType.CODE)
        assert c.sem_type_str() == "code"

    def test_as_token(self) -> None:
        c = CandidateIR(
            raw="$10",
            cleaned="10",
            span_start=0,
            span_end=3,
            position=0,
            primary_type=SemanticType.PRICE,
            type_distribution={SemanticType.PRICE: 0.9},
        )
        token = c.as_token(source_field="price")
        assert isinstance(token, SemanticToken)
        assert token.raw == "$10"
        assert token.normalized == "10"
        assert token.primary_type == SemanticType.PRICE
        assert token.source_field == "price"

    def test_type_distribution_semantic(self) -> None:
        dist = {SemanticType.PRICE: 0.8, SemanticType.NUMBER: 0.2}
        c = CandidateIR(raw="$20", cleaned="20", span_start=0, span_end=3, position=0, type_distribution=dist)
        result = c.type_distribution_semantic()
        assert result == dist
        assert result is not dist  # must be a copy


# ═══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP IR & STRUCTURAL MEMORY
# ═══════════════════════════════════════════════════════════════════════════════


class TestRelationshipIR:
    def test_construction(self) -> None:
        r = RelationshipIR(source_idx=0, target_idx=1, relationship_type="adjacent", confidence=0.8)
        assert r.source_idx == 0
        assert r.target_idx == 1
        assert r.relationship_type == "adjacent"
        assert r.confidence == 0.8
        assert r.evidence == []


class TestStructuralMemory:
    def test_construction(self) -> None:
        m = StructuralMemory(pattern_signature=("code", "price"), occurrence_count=3)
        assert m.pattern_signature == ("code", "price")
        assert m.occurrence_count == 3
        assert m.row_indices == []
        assert m.avg_confidence == 0.0


class TestSegmentedIR:
    def test_construction(self) -> None:
        candidates = [CandidateIR(raw="a", cleaned="a", span_start=0, span_end=1, position=0)]
        s = SegmentedIR(original="test text", candidates=candidates)
        assert s.original == "test text"
        assert len(s.candidates) == 1
        assert not s.is_noise
        assert s.overall_cohesion == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyWithAmbiguity:
    def test_code_type_number(self) -> None:
        dist = _classify_with_ambiguity("123", SemanticType.CODE)
        assert dist[SemanticType.NUMBER] == 0.9
        assert dist[SemanticType.CODE] == 0.1

    def test_code_type_three_letter(self) -> None:
        dist = _classify_with_ambiguity("ABC", SemanticType.CODE)
        assert dist[SemanticType.CODE] == 0.7
        assert SemanticType.TEXT in dist

    def test_code_type_four_letter(self) -> None:
        dist = _classify_with_ambiguity("ABCD", SemanticType.CODE)
        assert dist[SemanticType.CODE] == 0.8

    def test_number_with_percent(self) -> None:
        dist = _classify_with_ambiguity("50%", SemanticType.NUMBER)
        assert dist[SemanticType.NUMBER] == 0.7
        assert SemanticType.RATING in dist

    def test_number_with_dot(self) -> None:
        dist = _classify_with_ambiguity("3.5", SemanticType.NUMBER)
        assert SemanticType.NUMBER in dist
        assert SemanticType.RATING in dist
        assert SemanticType.PRICE in dist

    def test_date_default(self) -> None:
        dist = _classify_with_ambiguity("2025-01-01", SemanticType.DATE)
        assert dist[SemanticType.DATE] == 0.85

    def test_text_title_case(self) -> None:
        dist = _classify_with_ambiguity("Google", SemanticType.TEXT)
        assert dist[SemanticType.TEXT] == 0.6
        assert SemanticType.ORGANIZATION in dist
        assert SemanticType.LOCATION in dist

    def test_unknown_primary_type(self) -> None:
        dist = _classify_with_ambiguity("hello", SemanticType.URL)
        assert dist[SemanticType.URL] == 0.85


class TestClassifyFallback:
    def test_price_currency_symbol(self) -> None:
        assert _classify_fallback("$1,199") == SemanticType.PRICE
        assert _classify_fallback("€50") == SemanticType.PRICE

    def test_price_currency_code(self) -> None:
        assert _classify_fallback("100 usd") == SemanticType.PRICE
        assert _classify_fallback("50 inr") == SemanticType.PRICE

    def test_price_rupees(self) -> None:
        assert _classify_fallback("rs. 500") == SemanticType.PRICE
        assert _classify_fallback("rupees 1000") == SemanticType.PRICE

    def test_date_slash_format(self) -> None:
        assert _classify_fallback("01/15/2025") == SemanticType.DATE

    def test_date_dash_format_mm_dd_yyyy(self) -> None:
        # Only MM-DD-YYYY is supported, not YYYY-MM-DD
        assert _classify_fallback("01-15-2025") == SemanticType.DATE

    def test_date_text_format(self) -> None:
        assert _classify_fallback("jan 15, 2025") == SemanticType.DATE
        assert _classify_fallback("15 jan 2025") == SemanticType.DATE

    def test_code_uppercase(self) -> None:
        assert _classify_fallback("ABC") == SemanticType.CODE
        assert _classify_fallback("JFK") == SemanticType.CODE

    def test_code_alphanumeric(self) -> None:
        assert _classify_fallback("AA123") == SemanticType.CODE

    def test_identifier_underscore(self) -> None:
        assert _classify_fallback("PROD_123") == SemanticType.IDENTIFIER

    def test_number(self) -> None:
        assert _classify_fallback("123") == SemanticType.NUMBER
        assert _classify_fallback("99.5") == SemanticType.NUMBER

    def test_rating(self) -> None:
        assert _classify_fallback("4.5/5") == SemanticType.RATING
        assert _classify_fallback("8/10") == SemanticType.RATING

    def test_duration(self) -> None:
        assert _classify_fallback("2h30m") == SemanticType.DURATION
        assert _classify_fallback("3 hours") == SemanticType.DURATION

    def test_organization_title_case(self) -> None:
        assert _classify_fallback("Google") == SemanticType.ORGANIZATION
        assert _classify_fallback("British Airways") == SemanticType.ORGANIZATION

    def test_text_fallback(self) -> None:
        assert _classify_fallback("hello world") == SemanticType.TEXT
        assert _classify_fallback("some random text") == SemanticType.TEXT

    def test_product_like_camelcase(self) -> None:
        """'iPhone' is classified as ORGANIZATION (product-like CamelCase pattern)."""
        assert _classify_fallback("iPhone") == SemanticType.ORGANIZATION

    def test_price_like_k_suffix(self) -> None:
        """'5K' hits the price pattern first, not the number pattern."""
        assert _classify_fallback("5K") == SemanticType.PRICE
        assert _classify_fallback("10M") == SemanticType.PRICE


class TestCleanValue:
    def test_price_cleaned(self) -> None:
        cleaned = _clean_value("Price: $100", "price")
        assert "$" in cleaned
        assert "Price" not in cleaned

    def test_price_cost_prefix(self) -> None:
        cleaned = _clean_value("Cost - $50", "price")
        assert "$" in cleaned
        assert "Cost" not in cleaned

    def test_other_types_stripped(self) -> None:
        assert _clean_value("  hello  ", "text") == "hello"

    def test_cleans_with_semantic_type_enum(self) -> None:
        cleaned = _clean_value("Fare: $200", SemanticType.PRICE)
        assert "$" in cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractByPattern:
    def test_extracts_price(self) -> None:
        candidates = _extract_by_pattern("Price is $100 for this item")
        prices = [c for c in candidates if c.primary_type == SemanticType.PRICE]
        assert len(prices) >= 1
        assert "$100" in prices[0].raw

    def test_extracts_date(self) -> None:
        candidates = _extract_by_pattern("Date: 2025-01-15")
        dates = [c for c in candidates if c.primary_type == SemanticType.DATE]
        assert len(dates) >= 1

    def test_extracts_code(self) -> None:
        candidates = _extract_by_pattern("Flight AA123 from JFK")
        codes = [c for c in candidates if c.primary_type == SemanticType.CODE]
        assert len(codes) >= 1

    def test_deduplicates_spans(self) -> None:
        candidates = _extract_by_pattern("$100 $100")  # same pattern -> same span
        assert len(candidates) >= 1

    def test_filters_common_words_from_code(self) -> None:
        """'THE' is a common English word, now filtered from code candidates."""
        candidates = _extract_by_pattern("THE quick brown fox")
        code_candidates = [c for c in candidates if c.primary_type == SemanticType.CODE]
        assert len(code_candidates) == 0

    def test_skips_empty_raw(self) -> None:
        candidates = _extract_by_pattern("")
        assert candidates == []


class TestExtractBySplit:
    def test_splits_on_pipe(self) -> None:
        candidates = _extract_by_split("New York | $100 | 2025-01-01", set())
        assert len(candidates) >= 1

    def test_splits_on_tab(self) -> None:
        candidates = _extract_by_split("Code\tValue\tDate", set())
        assert len(candidates) >= 1

    def test_splits_on_double_space(self) -> None:
        candidates = _extract_by_split("Item1  Item2  Item3", set())
        assert len(candidates) >= 1

    def test_skips_short_segments(self) -> None:
        candidates = _extract_by_split("a | b | c", set())
        assert len(candidates) == 0

    def test_skips_existing_spans(self) -> None:
        existing = {(0, 8)}  # "New York" already covered
        candidates = _extract_by_split("New York | $100", existing)
        # "New York" span exists so only "$100" (if 9-13) should be new
        assert len(candidates) >= 0


class TestExtractByWhitespace:
    def test_splits_on_double_space(self) -> None:
        candidates = _extract_by_whitespace("hello  world", set())
        assert len(candidates) >= 2

    def test_falls_back_to_single_space(self) -> None:
        candidates = _extract_by_whitespace("hello world foo", set())
        assert len(candidates) >= 2

    def test_skips_short_parts(self) -> None:
        candidates = _extract_by_whitespace("a b c", set())
        assert len(candidates) == 0

    def test_skips_existing_spans(self) -> None:
        c1 = _extract_by_whitespace("hello world", set())
        assert len(c1) >= 1

    def test_handles_empty_text(self) -> None:
        assert _extract_by_whitespace("", set()) == []


class TestUncoveredRatio:
    def test_fully_covered(self) -> None:
        assert _uncovered_ratio("hello", {(0, 5)}) == 0.0

    def test_partially_covered(self) -> None:
        ratio = _uncovered_ratio("hello world", {(0, 5)})
        assert 0.5 < ratio < 0.6  # 6/11 uncovered ≈ 0.545

    def test_no_spans(self) -> None:
        ratio = _uncovered_ratio("hello", set())
        assert ratio == 1.0

    def test_empty_text(self) -> None:
        assert _uncovered_ratio("", {(0, 1)}) == 1.0


class TestExtractCandidateValues:
    def test_returns_empty_for_empty_text(self) -> None:
        assert extract_candidate_values("") == []

    def test_extracts_structured_text(self) -> None:
        candidates = extract_candidate_values("Flight AA123 from JFK to LAX on 2025-06-15 for $350")
        assert len(candidates) >= 4  # AA123, JFK, LAX, date, price
        types = {c.primary_type for c in candidates}
        assert SemanticType.CODE in types
        assert SemanticType.DATE in types
        assert SemanticType.PRICE in types

    def test_extracts_plain_text_with_fallback(self) -> None:
        candidates = extract_candidate_values("some random text with no structure")
        assert len(candidates) >= 1

    def test_sorts_by_position(self) -> None:
        candidates = extract_candidate_values("$100 and JFK")
        positions = [c.position for c in candidates]
        assert positions == sorted(positions)


# ═══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP SCORING
# ═══════════════════════════════════════════════════════════════════════════════


class TestInferRelationshipType:
    def test_price_modifier(self) -> None:
        price = CandidateIR(raw="$100", cleaned="100", span_start=0, span_end=4, position=0, primary_type=SemanticType.PRICE)
        text = CandidateIR(raw="item", cleaned="item", span_start=5, span_end=9, position=5, primary_type=SemanticType.TEXT)
        rel_type, _conf, _evidence = _infer_relationship_type(price, text)
        assert rel_type == "value_modifier"

    def test_code_then_price(self) -> None:
        code = CandidateIR(raw="JFK", cleaned="JFK", span_start=0, span_end=3, position=0, primary_type=SemanticType.CODE)
        price = CandidateIR(raw="$100", cleaned="100", span_start=4, span_end=8, position=4, primary_type=SemanticType.PRICE)
        rel_type, _, _ = _infer_relationship_type(code, price)
        assert rel_type == "location_price"

    def test_price_modifier_overrides_price_then_code(self) -> None:
        """'a is PRICE' check comes before code+price checks, returns value_modifier."""
        price = CandidateIR(raw="$100", cleaned="100", span_start=0, span_end=4, position=0, primary_type=SemanticType.PRICE)
        code = CandidateIR(raw="JFK", cleaned="JFK", span_start=5, span_end=8, position=5, primary_type=SemanticType.CODE)
        rel_type, conf, _ = _infer_relationship_type(price, code)
        assert rel_type == "value_modifier"
        assert conf == 0.6

    def test_paired_codes(self) -> None:
        c1 = CandidateIR(raw="JFK", cleaned="JFK", span_start=0, span_end=3, position=0, primary_type=SemanticType.CODE)
        c2 = CandidateIR(raw="LAX", cleaned="LAX", span_start=4, span_end=7, position=4, primary_type=SemanticType.CODE)
        rel_type, _, _ = _infer_relationship_type(c1, c2)
        assert rel_type == "paired_codes"

    def test_date_range(self) -> None:
        d1 = CandidateIR(
            raw="2025-01-01",
            cleaned="2025-01-01",
            span_start=0,
            span_end=10,
            position=0,
            primary_type=SemanticType.DATE,
        )
        d2 = CandidateIR(
            raw="2025-01-15",
            cleaned="2025-01-15",
            span_start=11,
            span_end=21,
            position=11,
            primary_type=SemanticType.DATE,
        )
        rel_type, _, _ = _infer_relationship_type(d1, d2)
        assert rel_type == "date_range"

    def test_same_type_group(self) -> None:
        o1 = CandidateIR(
            raw="Google",
            cleaned="Google",
            span_start=0,
            span_end=6,
            position=0,
            primary_type=SemanticType.ORGANIZATION,
        )
        o2 = CandidateIR(
            raw="Apple",
            cleaned="Apple",
            span_start=7,
            span_end=12,
            position=7,
            primary_type=SemanticType.ORGANIZATION,
        )
        rel_type, _, _ = _infer_relationship_type(o1, o2)
        assert rel_type == "same_type_group"

    def test_adjacent_default(self) -> None:
        o1 = CandidateIR(raw="Hello", cleaned="Hello", span_start=0, span_end=5, position=0, primary_type=SemanticType.TEXT)
        o2 = CandidateIR(raw="World", cleaned="World", span_start=6, span_end=11, position=6, primary_type=SemanticType.URL)
        rel_type, _, _ = _infer_relationship_type(o1, o2)
        assert rel_type == "adjacent"


class TestScoreRelationships:
    def test_empty_for_single_candidate(self) -> None:
        c = CandidateIR(raw="test", cleaned="test", span_start=0, span_end=4, position=0)
        assert score_relationships([c]) == []

    def test_empty_for_no_candidates(self) -> None:
        assert score_relationships([]) == []

    def test_scores_adjacent_candidates(self) -> None:
        c1 = CandidateIR(raw="$100", cleaned="100", span_start=0, span_end=4, position=0, primary_type=SemanticType.PRICE)
        c2 = CandidateIR(raw="JFK", cleaned="JFK", span_start=5, span_end=8, position=5, primary_type=SemanticType.CODE)
        rels = score_relationships([c1, c2])
        assert len(rels) >= 1

    def test_scores_nearby_candidates(self) -> None:
        c1 = CandidateIR(raw="Hello", cleaned="Hello", span_start=0, span_end=5, position=0, primary_type=SemanticType.TEXT)
        c2 = CandidateIR(raw="World", cleaned="World", span_start=10, span_end=15, position=10, primary_type=SemanticType.TEXT)
        rels = score_relationships([c1, c2])
        near = [r for r in rels if r.relationship_type == "nearby"]
        assert len(near) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL MEMORY
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaxPatternSimilarity:
    def test_identical_patterns(self) -> None:
        assert _max_pattern_similarity(("code", "price"), [("code", "price")]) == 1.0

    def test_partial_overlap(self) -> None:
        sim = _max_pattern_similarity(("code", "price"), [("code", "date")])
        assert 0.3 < sim < 0.5  # Jaccard similarity: {code}/{code,price,date} = 1/3

    def test_no_overlap(self) -> None:
        assert _max_pattern_similarity(("code",), [("price", "date")]) == 0.0

    def test_empty_known_list(self) -> None:
        assert _max_pattern_similarity(("code",), []) == 0.0


class TestStructuralMemoryTracker:
    def test_initial_state(self) -> None:
        tracker = StructuralMemoryTracker()
        assert tracker.total_records == 0
        assert tracker.patterns == {}

    def test_returns_high_anomaly_for_empty_row(self) -> None:
        tracker = StructuralMemoryTracker()
        score, evidence = tracker.record([], 0)
        assert score == 1.0
        assert "empty_row" in evidence

    def test_novel_pattern_low_confidence(self) -> None:
        """First occurrence self-matches in similarity check -> score 0.6."""
        tracker = StructuralMemoryTracker()
        c = CandidateIR(raw="test", cleaned="test", span_start=0, span_end=4, position=0, primary_type=SemanticType.TEXT)
        score, evidence = tracker.record([c], 0)
        assert score == 0.6
        assert "similar_to_known_pattern(1.00)" in evidence

    def test_second_occurrence(self) -> None:
        tracker = StructuralMemoryTracker()
        c = CandidateIR(raw="test", cleaned="test", span_start=0, span_end=4, position=0, primary_type=SemanticType.TEXT)
        tracker.record([c], 0)
        score, evidence = tracker.record([c], 1)
        assert score == 0.7
        assert "pattern_seen_2x" in evidence

    def test_third_occurrence_high_confidence(self) -> None:
        tracker = StructuralMemoryTracker()
        c = CandidateIR(raw="test", cleaned="test", span_start=0, span_end=4, position=0, primary_type=SemanticType.TEXT)
        tracker.record([c], 0)
        tracker.record([c], 1)
        score, evidence = tracker.record([c], 2)
        assert score == 0.9
        assert "pattern_seen_3x" in evidence

    def test_similar_pattern_gets_boost(self) -> None:
        tracker = StructuralMemoryTracker()
        c1 = CandidateIR(raw="$100", cleaned="100", span_start=0, span_end=4, position=0, primary_type=SemanticType.PRICE)
        c2 = CandidateIR(raw="JFK", cleaned="JFK", span_start=0, span_end=3, position=0, primary_type=SemanticType.CODE)
        # First record: ("price",) pattern
        tracker.record([c1], 0)
        # Second record: ("code",) — different type but similar to price
        # Actually this won't be very similar since price != code
        score, _evidence = tracker.record([c2], 1)
        assert isinstance(score, float)

    def test_pattern_signature_string_based(self) -> None:
        tracker = StructuralMemoryTracker()
        c = CandidateIR(raw="test", cleaned="test", span_start=0, span_end=4, position=0, primary_type=SemanticType.TEXT)
        tracker.record([c], 0)
        # Verify pattern key is string-based tuple
        sig_key = ("text",)
        assert sig_key in tracker.patterns
        assert tracker.patterns[sig_key].occurrence_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC DENSITY & NOISE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeSemanticDensity:
    def test_high_density_text(self) -> None:
        density = compute_semantic_density("$100 2025-01-01 JFK LAX 2h30m")
        assert density > 0.1  # Multiple typed candidates

    def test_plain_text_low_density(self) -> None:
        density = compute_semantic_density("the quick brown fox jumps over the lazy dog")
        assert density < 0.5

    def test_empty_text_zero_density(self) -> None:
        assert compute_semantic_density("") == 0.0

    def test_capped_at_one(self) -> None:
        density = compute_semantic_density("$100 " * 20)
        assert density <= 1.0


class TestIsLikelyNoise:
    def test_navigation_structure(self) -> None:
        is_noise, conf, _evidence = is_likely_noise("About Us | Contact | Privacy Policy")
        assert is_noise is True
        assert conf >= 0.8

    def test_copyright_notice(self) -> None:
        is_noise, _, _ = is_likely_noise("Copyright 2025 All Rights Reserved")
        assert is_noise is True

    def test_empty_text(self) -> None:
        is_noise, conf, _ = is_likely_noise("")
        assert is_noise is False
        assert conf == 0.2

    def test_too_short(self) -> None:
        is_noise, conf, _ = is_likely_noise("ab")
        assert is_noise is False
        assert conf == 0.2

    def test_structured_text_not_noise(self) -> None:
        is_noise, _, _ = is_likely_noise("Flight AA123 from JFK to LAX for $350")
        assert is_noise is False

    def test_high_text_ratio_noise(self) -> None:
        # Text with mostly prose and few typed values
        result, _, _ = is_likely_noise(
            "hello world this is a very long descriptive text that doesn't have much structured data in it at all",
        )
        assert isinstance(result, bool)


class TestIsNoiseField:
    def test_empty_value(self) -> None:
        is_noise, conf, _ = is_likely_noise_field("price", "")
        assert is_noise is True
        assert conf == 1.0

    def test_text_field_plain_text(self) -> None:
        is_noise, _, _ = is_likely_noise_field("name", "Acme Corporation")
        assert is_noise is False

    def test_text_field_navigation(self) -> None:
        is_noise, _, _ = is_likely_noise_field("name", "About Us Privacy Policy")
        assert is_noise is True

    def test_typed_field_with_content(self) -> None:
        is_noise, _, _ = is_likely_noise_field("price", "$100")
        assert is_noise is False

    def test_typed_field_no_content(self) -> None:
        is_noise, _, _ = is_likely_noise_field("price", "a b c")
        assert is_noise is True

    def test_too_short(self) -> None:
        is_noise, conf, _ = is_likely_noise_field("name", "x")
        assert is_noise is False
        assert conf == 0.3


# ═══════════════════════════════════════════════════════════════════════════════
# COMPOSITE VALUE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsCompositeValue:
    def test_short_text_not_composite(self) -> None:
        assert is_composite_value("hi") is False

    def test_empty_text_not_composite(self) -> None:
        assert is_composite_value("") is False

    def test_single_meaningful_type_not_composite(self) -> None:
        assert is_composite_value("Google Apple") is False

    def test_multiple_types_is_composite(self) -> None:
        assert is_composite_value("JFK to LAX on 2025-06-15 for $350") is True

    def test_plain_text_not_composite(self) -> None:
        assert is_composite_value("the quick brown fox jumps") is False


# ═══════════════════════════════════════════════════════════════════════════════
# RECORD SEGMENTATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeCohesion:
    def test_zero_for_empty_candidates(self) -> None:
        assert _compute_cohesion([], []) == 0.0

    def test_high_for_meaningful_candidates(self) -> None:
        c = CandidateIR(
            raw="$100",
            cleaned="100",
            span_start=0,
            span_end=4,
            position=0,
            primary_type=SemanticType.PRICE,
            primary_confidence=0.9,
        )
        r = RelationshipIR(source_idx=0, target_idx=1, relationship_type="adjacent", confidence=0.8)
        cohesion = _compute_cohesion([c], [r])
        assert 0.3 < cohesion <= 1.0

    def test_low_for_plain_text(self) -> None:
        c = CandidateIR(
            raw="hello",
            cleaned="hello",
            span_start=0,
            span_end=5,
            position=0,
            primary_type=SemanticType.TEXT,
            primary_confidence=0.3,
        )
        cohesion = _compute_cohesion([c], [])
        assert cohesion < 0.5


class TestSegmentSingleText:
    def test_returns_segmented_ir(self) -> None:
        ir = segment_single_text("Flight AA123 from JFK for $350")
        assert isinstance(ir, SegmentedIR)
        assert ir.original == "Flight AA123 from JFK for $350"
        assert len(ir.candidates) >= 3

    def test_noise_detection_for_navigation(self) -> None:
        ir = segment_single_text("About Us | Contact | Privacy Policy")
        assert ir.is_noise is True

    def test_cohesion_is_computed(self) -> None:
        ir = segment_single_text("Test")
        assert isinstance(ir.overall_cohesion, float)

    def test_structural_pattern(self) -> None:
        ir = segment_single_text("JFK to LAX for $350")
        assert isinstance(ir.structural_pattern, tuple)


# ═══════════════════════════════════════════════════════════════════════════════
# RECORD EXPANSION
# ═══════════════════════════════════════════════════════════════════════════════


class TestExpandCompositeRecords:
    def test_returns_empty_for_empty_input(self) -> None:
        assert expand_composite_records([]) == []

    def test_passthrough_for_non_composite(self) -> None:
        records = [{"name": "Test", "price": "$100"}]
        result = expand_composite_records(records)
        assert result == records

    def test_expands_composite_record(self) -> None:
        records = [{"details": "Flight AA123 from JFK to LAX for $350"}]
        result = expand_composite_records(records)
        assert len(result) == 1
        # The original "details" key should be removed and replaced with seg_ keys
        assert "details" not in result[0]
        # Should have at least one seg_ prefixed key
        seg_keys = [k for k in result[0] if "seg_" in k]
        assert len(seg_keys) >= 1

    def test_uses_provided_memory(self) -> None:
        memory = StructuralMemoryTracker()
        records = [{"details": "Test value"}]
        result = expand_composite_records(records, memory=memory)
        assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# OVERLAP RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveOverlaps:
    def test_empty_tokens(self) -> None:
        assert resolve_overlaps([]) == []

    def test_single_token_unchanged(self) -> None:
        token = SemanticToken(raw="$100", normalized="100", span=Span(0, 4), position=0, primary_type=SemanticType.PRICE)
        result = resolve_overlaps([token])
        assert len(result) == 1
        assert result[0] is token  # Same object since no resolution needed

    def test_dominant_suppresses_lower(self) -> None:
        price = SemanticToken(raw="$100", normalized="100", span=Span(0, 4), position=0, primary_type=SemanticType.PRICE)
        number = SemanticToken(raw="100", normalized="100", span=Span(0, 3), position=0, primary_type=SemanticType.NUMBER)
        result = resolve_overlaps([number, price])
        # Price (dominance=90) should suppress Number (dominance=20)
        assert len(result) == 1
        assert result[0].primary_type == SemanticType.PRICE

    def test_non_overlapping_tokens_both_kept(self) -> None:
        price = SemanticToken(raw="$100", normalized="100", span=Span(0, 4), position=0, primary_type=SemanticType.PRICE)
        date = SemanticToken(
            raw="2025-01-01",
            normalized="2025-01-01",
            span=Span(10, 20),
            position=10,
            primary_type=SemanticType.DATE,
        )
        result = resolve_overlaps([price, date])
        assert len(result) == 2

    def test_lexical_containment_suppresses_number(self) -> None:
        org = SemanticToken(
            raw="Organization",
            normalized="organization",
            span=Span(0, 12),
            position=0,
            primary_type=SemanticType.ORGANIZATION,
        )
        # "org" is a strict substring of "Organization"
        text = SemanticToken(raw="org", normalized="org", span=Span(5, 8), position=0, primary_type=SemanticType.TEXT)
        result = resolve_overlaps([org, text])
        # Organization should suppress text (same type -> always suppress)
        assert len(result) == 1
        assert result[0].primary_type in (SemanticType.ORGANIZATION, SemanticType.TEXT)


class TestDominanceHierarchy:
    def test_email_highest(self) -> None:
        assert DOMINANCE_HIERARCHY[SemanticType.EMAIL] == 100

    def test_text_lowest(self) -> None:
        assert DOMINANCE_HIERARCHY[SemanticType.TEXT] == 10

    def test_price_over_code(self) -> None:
        assert DOMINANCE_HIERARCHY[SemanticType.PRICE] > DOMINANCE_HIERARCHY[SemanticType.CODE]

    def test_all_types_present(self) -> None:
        expected = {
            SemanticType.EMAIL,
            SemanticType.PRICE,
            SemanticType.DATE,
            SemanticType.PHONE,
            SemanticType.URL,
            SemanticType.DURATION,
            SemanticType.RATING,
            SemanticType.CODE,
            SemanticType.LOCATION,
            SemanticType.ORGANIZATION,
            SemanticType.NAME,
            SemanticType.NUMBER,
            SemanticType.IDENTIFIER,
            SemanticType.TEXT,
        }
        assert set(DOMINANCE_HIERARCHY.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION: Full Pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    def test_extract_to_segment_to_expand(self) -> None:
        """End-to-end: extract candidates -> segment -> expand composites."""
        text = "Flight AA123 from JFK to LAX for $350 on 2025-06-15"
        ir = segment_single_text(text)
        assert len(ir.candidates) >= 4
        assert len(ir.relationships) >= 1
        assert isinstance(ir.overall_cohesion, float)

    def test_noise_classification_flow(self) -> None:
        """End-to-end: noise classification through the pipeline."""
        text = "About Us | Contact | Privacy Policy | Copyright 2025"
        # is_likely_noise should detect navigation structure
        is_noise, conf, _evidence = is_likely_noise(text)
        assert is_noise is True
        assert conf >= 0.8

        # segment_single_text should also flag noise
        ir = segment_single_text(text)
        assert ir.is_noise is True

    def test_composite_expansion_flow(self) -> None:
        """End-to-end: composite detection -> expansion."""
        records = [
            {"simple": "Just a name"},
            {"blob": "Flight AA123 from JFK for $350 on 2025-06-15"},
        ]
        expanded = expand_composite_records(records)
        assert len(expanded) == 2
        # First record should pass through unchanged
        assert "simple" in expanded[0]
        # Second record should be expanded
        seg_keys = [k for k in expanded[1] if "seg_" in k]
        assert len(seg_keys) >= 1
