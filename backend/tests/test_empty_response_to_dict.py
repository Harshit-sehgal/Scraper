"""Tests for EmptyResponseCheck.to_dict()."""

from __future__ import annotations

from app.empty_response_detector import EmptyResponseCheck, detect_empty_response


class TestEmptyResponseCheckToDict:
    """Verify to_dict serializes the dataclass for classification/telemetry."""

    def test_to_dict_returns_all_fields(self) -> None:
        """to_dict must include all serializable fields."""
        result = EmptyResponseCheck(
            is_empty=False,
            empty_type="blank",
            confidence=0.0,
            message="no issue",
            text_length=100,
            data_signals=5,
            suggestions=[],
        )
        d = result.to_dict()
        assert d["is_empty"] is False
        assert d["empty_type"] == "blank"
        assert d["confidence"] == 0.0
        assert d["message"] == "no issue"
        assert d["text_length"] == 100
        assert d["data_signals"] == 5

    def test_to_dict_includes_nonempty_suggestions(self) -> None:
        """Suggestions list must appear in output when non-empty."""
        result = EmptyResponseCheck(
            is_empty=True,
            empty_type="cookie_wall",
            confidence=0.95,
            message="blocked",
            text_length=10,
            data_signals=0,
            suggestions=["disable cookies", "use a different agent"],
        )
        d = result.to_dict()
        assert "suggestions" in d
        assert len(d["suggestions"]) == 2

    def test_to_dict_omits_empty_suggestions(self) -> None:
        """Empty suggestions list must not appear (tidy serialization)."""
        result = EmptyResponseCheck(
            is_empty=True,
            empty_type="blank",
            confidence=1.0,
            message="blank",
            text_length=0,
            data_signals=0,
            suggestions=[],
        )
        d = result.to_dict()
        assert "suggestions" not in d

    def test_to_dict_keys_are_strings(self) -> None:
        """All keys must be strings (not `[]` weirdness)."""
        result = detect_empty_response("")
        d = result.to_dict()
        for key in d:
            assert isinstance(key, str)


class TestScraperEmptyCheckUsage:
    """Verify the scraper's EmptyResponseCheck path type-checks clean."""

    def test_detect_empty_response_returns_to_dict_callable(self) -> None:
        """detect_empty_response must return an object with to_dict()."""
        result = detect_empty_response("<html></html>")
        assert hasattr(result, "to_dict")
        d = result.to_dict()
        assert isinstance(d, dict)
