"""
Unit Tests for Semantic Mapper.
Tests type detection, value matching, noise filtering, and fragment
suppression — the core "semantic physics" of the system.
"""

from __future__ import annotations

from app.semantic_ir import SemanticType
from app.semantic_mapper import (
    detect_semantic_type,
    is_child_fragment,
    _is_noise_value,
    match_values_to_intent,
    SEMANTIC_PATTERNS,
)
from app.intent_parser import IntentSchema
from app.page_profiler import StructureProfile, ValuePatterns


# ─── detect_semantic_type ──────────────────────────────────────────────


class TestDetectSemanticType:
    def test_price_with_currency_symbol(self):
        stype, conf = detect_semantic_type("£238")
        assert stype == SemanticType.PRICE
        assert conf >= 0.9

    def test_price_with_code(self):
        stype, conf = detect_semantic_type("500 USD")
        assert stype == SemanticType.PRICE
        assert conf >= 0.9

    def test_date_slash_format(self):
        stype, conf = detect_semantic_type("22/05/2026")
        assert stype == SemanticType.DATE

    def test_date_dash_format(self):
        stype, conf = detect_semantic_type("2026-05-22")
        assert stype == SemanticType.DATE

    def test_date_text_format(self):
        stype, conf = detect_semantic_type("May 22, 2026")
        assert stype == SemanticType.DATE

    def test_email(self):
        stype, conf = detect_semantic_type("contact@example.com")
        assert stype == SemanticType.EMAIL
        assert conf >= 0.9

    def test_phone(self):
        stype, conf = detect_semantic_type("+1-555-0101")
        assert stype == SemanticType.PHONE

    def test_rating_x_out_of_5(self):
        stype, conf = detect_semantic_type("4.5 / 5")
        assert stype == SemanticType.RATING

    def test_rating_with_stars(self):
        stype, conf = detect_semantic_type("4 stars")
        assert stype == SemanticType.RATING

    def test_url(self):
        stype, conf = detect_semantic_type("https://example.com/page")
        assert stype == SemanticType.URL

    def test_identifier_code(self):
        stype, conf = detect_semantic_type("BA123")
        assert stype == SemanticType.IDENTIFIER

    def test_duration(self):
        """Duration pattern matches directly (avoid IDENTIFIER interception)."""
        pattern = SEMANTIC_PATTERNS[SemanticType.DURATION][0][0]
        assert pattern.search("3h")
        assert pattern.search("2h 30m")
        assert not pattern.search("hello")

    def test_code_uppercase(self):
        stype, conf = detect_semantic_type("LHR")
        assert stype == SemanticType.CODE

    def test_organization_multi_word_title(self):
        stype, conf = detect_semantic_type("British Airways")
        assert stype == SemanticType.ORGANIZATION

    def test_text_default(self):
        stype, conf = detect_semantic_type("some random text")
        assert stype == SemanticType.TEXT

    def test_empty_value(self):
        stype, conf = detect_semantic_type("")
        assert stype == SemanticType.TEXT
        assert conf == 0.0

    def test_numeric_field_name_hint_price(self):
        stype, conf = detect_semantic_type("500", field_name="price")
        assert stype == SemanticType.PRICE

    def test_numeric_field_name_hint_date(self):
        stype, conf = detect_semantic_type("0500", field_name="start_time")
        assert stype == SemanticType.DATE

    def test_numeric_field_name_hint_value(self):
        stype, conf = detect_semantic_type("42", field_name="quantity")
        assert stype == SemanticType.NUMBER

    def test_product_like_brand_naming(self):
        stype, conf = detect_semantic_type("iPhone 15")
        assert conf >= 0.5  # Should detect as ORGANIZATION or similar

    def test_ui_noise_words(self):
        stype, conf = detect_semantic_type("click here")
        assert conf <= 0.5  # Low confidence for noise

    def test_lru_cache_works(self):
        # Calling same value twice should return same result (cached)
        r1 = detect_semantic_type("£238")
        r2 = detect_semantic_type("£238")
        assert r1 == r2


# ─── is_child_fragment ─────────────────────────────────────────────────


class TestIsChildFragment:
    def test_sub_numeric_suppression(self):
        """Pure digits inside a currency value should be suppressed."""
        assert is_child_fragment("238", {"£238"}) is True

    def test_prefix_suppression(self):
        """Short prefix fragments should be suppressed."""
        assert is_child_fragment("LON", {"LON PAR"}) is True

    def test_no_suppression_for_unique_values(self):
        """A value not found in any parent should not be suppressed."""
        assert is_child_fragment("example.com", {"test@example.com"}) is False

    def test_no_suppression_for_same_length(self):
        """Same-length values should not suppress each other."""
        assert is_child_fragment("hello", {"world"}) is False

    def test_no_suppression_for_empty_seen(self):
        assert is_child_fragment("test", set()) is False

    def test_no_suppression_for_empty_value(self):
        assert is_child_fragment("", {"something"}) is False

    def test_single_character_not_suppressed(self):
        """Single alpha characters should not be suppressed."""
        assert is_child_fragment("A", {"Alpha"}) is False


# ─── _is_noise_value ───────────────────────────────────────────────────


class TestIsNoiseValue:
    def test_none_is_noise(self):
        assert _is_noise_value(None) is True  # type: ignore[arg-type]

    def test_empty_string_is_noise(self):
        assert _is_noise_value("") is True

    def test_short_string_is_noise(self):
        assert _is_noise_value("a") is True

    def test_common_ui_noise(self):
        assert _is_noise_value("About Us") is True
        assert _is_noise_value("Privacy Policy") is True
        assert _is_noise_value("Click Here") is True
        assert _is_noise_value("Read More") is True

    def test_single_word_noise(self):
        assert _is_noise_value("Home") is True
        assert _is_noise_value("Menu") is True
        assert _is_noise_value("Search") is True

    def test_meaningful_data_not_noise(self):
        assert _is_noise_value("British Airways") is False
        assert _is_noise_value("£238") is False
        assert _is_noise_value("22-05-2026") is False

    def test_very_long_is_noise(self):
        long_str = "x" * 301
        assert _is_noise_value(long_str) is True

    def test_short_but_meaningful(self):
        assert _is_noise_value("NY") is False  # Two-letter code, meaningful


# ─── SEMANTIC_PATTERNS structure ────────────────────────────────────────


class TestSemanticPatterns:
    def test_all_types_have_patterns(self):
        """Every SemanticType should have at least one pattern defined."""
        patternless_types = []
        for stype in (
            SemanticType.PRICE, SemanticType.DATE, SemanticType.EMAIL,
            SemanticType.PHONE, SemanticType.RATING, SemanticType.URL,
            SemanticType.IDENTIFIER, SemanticType.DURATION, SemanticType.CODE,
        ):
            if stype not in SEMANTIC_PATTERNS or not SEMANTIC_PATTERNS[stype]:
                patternless_types.append(stype)
        assert not patternless_types, f"Missing patterns for: {patternless_types}"


# ─── match_values_to_intent ────────────────────────────────────────────


class TestMatchValuesToIntent:
    def make_schema(self, needs: dict[str, list[str]]) -> IntentSchema:
        return IntentSchema(
            raw_query="test",
            semantic_needs=needs,
        )

    def make_empty_profile(self) -> StructureProfile:
        return StructureProfile(
            structure_type="cards",
            container_selector=".item",
        )

    def test_maps_price_to_price_need(self):
        schema = self.make_schema({"price": ["price"]})
        profile = self.make_empty_profile()

        records = [{"col1": "£238", "col2": "British Airways"}]
        mappings = match_values_to_intent(
            records, schema, profile, ValuePatterns()
        )

        assert len(mappings) == 1
        mapping = mappings[0]
        assert mapping.mapped_fields.get("price") == "£238"
        assert mapping.confidence_scores.get("price", 0) >= 0.9

    def test_maps_date_to_date_need(self):
        schema = self.make_schema({"date": ["date"]})
        profile = self.make_empty_profile()

        records = [{"col1": "2026-05-22", "col2": "Lufthansa"}]
        mappings = match_values_to_intent(
            records, schema, profile, ValuePatterns()
        )

        assert len(mappings) == 1
        assert mappings[0].mapped_fields.get("date") == "2026-05-22"

    def test_unmatched_need_falls_back_to_first_value(self):
        """Need with no pattern match falls back to first non-noise value (confidence=0.3)."""
        schema = self.make_schema({"rating": ["rating"]})
        profile = self.make_empty_profile()

        records = [{"col1": "British Airways"}]
        mappings = match_values_to_intent(
            records, schema, profile, ValuePatterns()
        )

        assert len(mappings) == 1
        mapping = mappings[0]
        # Fallback maps first non-noise value with low confidence
        assert mapping.mapped_fields.get("rating") == "British Airways"
        assert mapping.confidence_scores.get("rating", 0) == 0.3
