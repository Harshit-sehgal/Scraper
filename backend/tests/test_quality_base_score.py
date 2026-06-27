"""F-QUALITY-001: Tighten quality base score to reduce false positives.

Verifies that:
1. Placeholder values ("N/A", "None", "TBD", etc.) score 0.0
2. Short/non-descriptive text like "Click here" scores low
3. Meaningful text still scores above the presence threshold
4. QUALITY_BASE_SCORE is significantly lower than legacy 0.3
"""

from __future__ import annotations

import pytest
from app.config import settings
from app.models import FieldType, SchemaField
from app.utils.quality import _value_quality, score_record_quality


def _sf(name: str, ftype: FieldType = FieldType.STRING, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=ftype, description="", required=required)


class TestPlaceholderZeroScore:
    """Common placeholder text must score 0.0."""

    @pytest.mark.parametrize(
        "value",
        [
            "N/A",
            "n/a",
            "NA",
            "na",
            "None",
            "none",
            "TBD",
            "tbd",
            "TBA",
            "null",
            "undefined",
            "-",
            "--",
            "---",
            "N.A.",
            "n.a.",
            "Not Available",
            "Not Applicable",
        ],
    )
    def test_placeholder_scores_zero(self, value: str) -> None:
        field = _sf("company_name")
        assert _value_quality(field, value) == 0.0, f"Placeholder '{value}' must score 0.0"

    def test_normal_text_not_zero(self) -> None:
        """Real text must still score above 0."""
        field = _sf("company_name")
        score = _value_quality(field, "Acme Corporation")
        assert score > 0.0, "Real company name must score > 0"


class TestBaseScoreToLower:
    """Verify QUALITY_BASE_SCORE was lowered from 0.3."""

    def test_base_score_is_tight(self) -> None:
        assert settings.QUALITY_BASE_SCORE < 0.2, (
            f"QUALITY_BASE_SCORE should be < 0.2 to reduce false positives, got {settings.QUALITY_BASE_SCORE}"
        )

    def test_present_threshold_raised(self) -> None:
        assert settings.QUALITY_PRESENT_FIELD_THRESHOLD >= 0.25, (
            f"QUALITY_PRESENT_FIELD_THRESHOLD should be >= 0.25, got {settings.QUALITY_PRESENT_FIELD_THRESHOLD}"
        )


class TestShortNoisePenalty:
    """Short non-descriptive text must score below the presence threshold."""

    def test_click_here_scores_low(self) -> None:
        field = _sf("title")
        score = _value_quality(field, "Click here")
        assert score < settings.QUALITY_PRESENT_FIELD_THRESHOLD, (
            f"'Click here' must score below presence threshold ({settings.QUALITY_PRESENT_FIELD_THRESHOLD}), got {score}"
        )

    def test_read_more_scores_low(self) -> None:
        field = _sf("company_name")
        score = _value_quality(field, "Read more")
        assert score < settings.QUALITY_PRESENT_FIELD_THRESHOLD, f"'Read more' must score below presence threshold, got {score}"

    def test_na_in_identity_field_zero(self) -> None:
        field = _sf("name")
        assert _value_quality(field, "N/A") == 0.0


class TestRecordLevelScoring:
    """Record-level quality must reject junk records."""

    def test_record_with_na_fields_scores_low(self) -> None:
        fields = [
            _sf("name", FieldType.STRING, required=True),
            _sf("price", FieldType.CURRENCY, required=True),
        ]
        record = {"name": "N/A", "price": "N/A"}
        score = score_record_quality(record, fields)
        assert score < settings.QUALITY_REQUIRED_MISSING_THRESHOLD, (
            f"Record with both N/A fields must score very low, got {score}"
        )

    def test_record_with_real_data_scores_high(self) -> None:
        fields = [
            _sf("name", FieldType.STRING, required=True),
            _sf("price", FieldType.CURRENCY, required=True),
        ]
        record = {"name": 'Apple MacBook Pro 16"', "price": "$2,499"}
        score = score_record_quality(record, fields)
        assert score > 0.5, f"Real product record must score above 0.5, got {score}"

    def test_empty_required_field_reduces_score(self) -> None:
        fields = [
            _sf("title", FieldType.STRING, required=True),
            _sf("description", FieldType.STRING, required=False),
        ]
        # title is empty string → 0.0
        record = {"title": "", "description": "A properly long description of something useful"}
        score = score_record_quality(record, fields)
        # With a missing required field, cohesion penalty kicks in
        assert score < 0.6, f"Missing required field should reduce score, got {score}"
