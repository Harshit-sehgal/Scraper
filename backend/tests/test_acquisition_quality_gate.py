"""Tests for acquisition quality gates."""

from app.acquisition_quality_gate import (
    assess_acquisition_quality,
    quality_summary,
    should_proceed_with_acquisition,
)


class TestAssessAcquisitionQuality:
    """Tests for assess_acquisition_quality."""

    def test_high_quality_returns_pass(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=1.0,
                anti_bot_score=1.0,
                visible_text_length=1000,
            )
            == "pass"
        )

    def test_low_data_evidence_score_returns_block(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=0.2,
                anti_bot_score=1.0,
                visible_text_length=1000,
            )
            == "block"
        )

    def test_low_anti_bot_score_returns_block(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=1.0,
                anti_bot_score=0.1,
                visible_text_length=1000,
            )
            == "block"
        )

    def test_low_visible_text_length_returns_review(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=1.0,
                anti_bot_score=1.0,
                visible_text_length=30,
            )
            == "review"
        )

    def test_edge_case_data_evidence_exactly_0_3_returns_pass(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=0.3,
                anti_bot_score=1.0,
                visible_text_length=1000,
            )
            == "pass"
        )

    def test_edge_case_anti_bot_exactly_0_2_returns_pass(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=1.0,
                anti_bot_score=0.2,
                visible_text_length=1000,
            )
            == "pass"
        )

    def test_edge_case_visible_text_exactly_50_returns_pass(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=1.0,
                anti_bot_score=1.0,
                visible_text_length=50,
            )
            == "pass"
        )

    def test_multiple_failures_block_takes_precedence(self) -> None:
        assert (
            assess_acquisition_quality(
                data_evidence_score=0.1,
                anti_bot_score=0.1,
                visible_text_length=10,
            )
            == "block"
        )


class TestShouldProceedWithAcquisition:
    """Tests for should_proceed_with_acquisition."""

    def test_pass_returns_true(self) -> None:
        assert (
            should_proceed_with_acquisition(
                data_evidence_score=1.0,
                anti_bot_score=1.0,
                visible_text_length=1000,
            )
            is True
        )

    def test_review_returns_true(self) -> None:
        assert (
            should_proceed_with_acquisition(
                data_evidence_score=1.0,
                anti_bot_score=1.0,
                visible_text_length=30,
            )
            is True
        )

    def test_block_data_evidence_returns_false(self) -> None:
        assert (
            should_proceed_with_acquisition(
                data_evidence_score=0.2,
                anti_bot_score=1.0,
                visible_text_length=1000,
            )
            is False
        )

    def test_block_anti_bot_returns_false(self) -> None:
        assert (
            should_proceed_with_acquisition(
                data_evidence_score=1.0,
                anti_bot_score=0.1,
                visible_text_length=1000,
            )
            is False
        )


class TestQualitySummary:
    """Tests for quality_summary."""

    def test_summary_contains_all_keys(self) -> None:
        summary = quality_summary(
            data_evidence_score=1.0,
            anti_bot_score=1.0,
            visible_text_length=1000,
        )
        assert set(summary.keys()) == {
            "data_evidence_score",
            "anti_bot_score",
            "visible_text_length",
            "result",
        }

    def test_summary_values_match(self) -> None:
        summary = quality_summary(
            data_evidence_score=0.5,
            anti_bot_score=0.7,
            visible_text_length=200,
        )
        assert summary["data_evidence_score"] == 0.5
        assert summary["anti_bot_score"] == 0.7
        assert summary["visible_text_length"] == 200
        assert summary["result"] == "pass"

    def test_summary_block_result(self) -> None:
        summary = quality_summary(
            data_evidence_score=0.1,
            anti_bot_score=1.0,
            visible_text_length=1000,
        )
        assert summary["result"] == "block"

    def test_summary_review_result(self) -> None:
        summary = quality_summary(
            data_evidence_score=1.0,
            anti_bot_score=1.0,
            visible_text_length=20,
        )
        assert summary["result"] == "review"
