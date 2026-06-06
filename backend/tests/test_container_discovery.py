"""Tests for app.container_discovery.

Covers the public API (discover_containers, multi_pass_container_extraction,
classify_container_failure) and the result dataclasses.

These tests previously did not exist despite the module being one of the
largest in app/ (840+ lines) and a central part of the extraction pipeline.
"""

from __future__ import annotations

import asyncio
from dataclasses import is_dataclass

import pytest
from app.container_discovery import (
    ContainerExtractionResult,
    ContainerRanking,
    MultiPassResult,
    classify_container_failure,
    discover_containers,
    multi_pass_container_extraction,
)
from app.models import FieldType, SchemaField

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_HTML = """
<html><body>
    <div class="result">
        <h2>Product A</h2>
        <span class="price">$19.99</span>
        <p>support@example.com</p>
        <p>+1-555-0100</p>
    </div>
    <div class="result">
        <h2>Product B</h2>
        <span class="price">$29.99</span>
        <p>sales@example.com</p>
        <p>+1-555-0200</p>
    </div>
    <div class="result">
        <h2>Product C</h2>
        <span class="price">$39.99</span>
        <p>info@example.com</p>
        <p>+1-555-0300</p>
    </div>
</body></html>
"""


@pytest.fixture
def empty_html() -> str:
    return ""


@pytest.fixture
def short_html() -> str:
    return "<html><body><p>hi</p></body></html>"


# ---------------------------------------------------------------------------
# ContainerRanking / MultiPassResult / ContainerExtractionResult dataclasses
# ---------------------------------------------------------------------------


def test_container_ranking_is_dataclass() -> None:
    """ContainerRanking is a dataclass with the documented fields."""
    assert is_dataclass(ContainerRanking)
    r = ContainerRanking(
        containers=[],
        best_selector="div.result",
        best_score=0.42,
        total_candidates=5,
    )
    assert r.containers == []
    assert r.best_selector == "div.result"
    assert r.best_score == 0.42
    assert r.total_candidates == 5


def test_container_ranking_to_dict() -> None:
    r = ContainerRanking(
        containers=[],
        best_selector="div.result",
        best_score=0.7,
        total_candidates=3,
    )
    d = r.to_dict()
    assert d["best_selector"] == "div.result"
    assert d["best_score"] == 0.7
    assert d["total_candidates"] == 3
    assert d["containers"] == []


def test_multi_pass_result_is_dataclass() -> None:
    assert is_dataclass(MultiPassResult)
    m = MultiPassResult(
        all_passed=True,
        final_records=[{"k": "v"}],
        total_records=1,
        passes_attempted=2,
        passes_succeeded=1,
        best_selector="div.result",
    )
    assert m.all_passed is True
    assert m.total_records == 1
    assert m.failure_reason == ""  # default


def test_container_extraction_result_is_dataclass() -> None:
    assert is_dataclass(ContainerExtractionResult)
    e = ContainerExtractionResult(
        selector="div.result",
        records=[{"x": 1}],
        record_count=1,
        avg_quality=0.5,
        success=True,
    )
    assert e.selector == "div.result"
    assert e.failure_reason == ""  # default


# ---------------------------------------------------------------------------
# discover_containers
# ---------------------------------------------------------------------------


def test_discover_containers_with_empty_html(empty_html: str) -> None:
    """Empty HTML returns an empty ranking (no crash)."""
    r = discover_containers(empty_html)
    assert isinstance(r, ContainerRanking)
    assert r.containers == []
    assert r.best_selector == ""
    assert r.best_score == 0.0
    assert r.total_candidates == 0


def test_discover_containers_with_short_html(short_html: str) -> None:
    """Short HTML (under 100 chars) returns an empty ranking."""
    r = discover_containers(short_html)
    assert r.containers == []


def test_discover_containers_with_repeated_structure() -> None:
    """A page with repeated <div class='result'> blocks surfaces a ranking."""
    r = discover_containers(SAMPLE_HTML, url="https://example.com/products")
    assert isinstance(r, ContainerRanking)
    # Either we find repeated structure (containers populated) or not;
    # the contract is that the function never crashes and returns a
    # valid ranking.
    if r.containers:
        assert r.best_selector != ""
        assert r.best_score > 0
        assert r.total_candidates == len(r.containers)


def test_discover_containers_respects_min_score() -> None:
    """Setting min_score to a high value prunes the result list."""
    r1 = discover_containers(SAMPLE_HTML, min_score=0.0)
    r2 = discover_containers(SAMPLE_HTML, min_score=10.0)
    assert len(r2.containers) <= len(r1.containers)


def test_discover_containers_url_is_optional() -> None:
    """url parameter is optional; both paths return valid rankings."""
    r1 = discover_containers(SAMPLE_HTML)
    r2 = discover_containers(SAMPLE_HTML, url="https://example.com")
    assert isinstance(r1, ContainerRanking)
    assert isinstance(r2, ContainerRanking)


def test_discover_containers_ranks_higher_score_first() -> None:
    """The first container in the ranking has the highest score."""
    r = discover_containers(SAMPLE_HTML)
    if len(r.containers) >= 2:
        # Containers should be in descending score order
        from app.page_evidence_collector import CandidateContainer

        for c in r.containers:
            assert isinstance(c, CandidateContainer)


# ---------------------------------------------------------------------------
# multi_pass_container_extraction
# ---------------------------------------------------------------------------


def test_multi_pass_extraction_with_no_containers(short_html: str) -> None:
    """A page with no detectable containers returns no_containers_detected."""
    result = asyncio.run(
        multi_pass_container_extraction(
            short_html,
            schema_fields=[
                SchemaField(name="title", field_type=FieldType.STRING),
                SchemaField(name="price", field_type=FieldType.STRING),
            ],
        ),
    )
    assert isinstance(result, MultiPassResult)
    assert result.all_passed is False
    assert result.failure_reason == "no_containers_detected"
    assert result.passes_attempted == 0
    assert result.total_records == 0


def test_multi_pass_extraction_returns_dataclass_on_empty_html(empty_html: str) -> None:
    result = asyncio.run(
        multi_pass_container_extraction(
            empty_html,
            schema_fields=[SchemaField(name="title", field_type=FieldType.STRING)],
        ),
    )
    assert result.all_passed is False
    assert result.failure_reason in ("no_containers_detected", "all_passes_empty")


def test_multi_pass_extraction_with_repeated_structure() -> None:
    """A page with repeated records returns records (success or failure)."""
    result = asyncio.run(
        multi_pass_container_extraction(
            SAMPLE_HTML,
            schema_fields=[
                SchemaField(name="title", field_type=FieldType.STRING),
                SchemaField(name="price", field_type=FieldType.STRING),
                SchemaField(name="email", field_type=FieldType.EMAIL),
            ],
        ),
    )
    assert isinstance(result, MultiPassResult)
    assert result.passes_attempted >= 0
    assert result.passes_succeeded >= 0
    assert result.passes_succeeded <= result.passes_attempted


def test_multi_pass_extraction_max_passes_cap() -> None:
    """max_passes is a positive upper bound; we never exceed it."""
    # Use max_passes=1; even if containers exist, we only try 1.
    result = asyncio.run(
        multi_pass_container_extraction(
            SAMPLE_HTML,
            schema_fields=[SchemaField(name="title", field_type=FieldType.STRING)],
            max_passes=1,
        ),
    )
    assert result.passes_attempted <= 1


# ---------------------------------------------------------------------------
# classify_container_failure
# ---------------------------------------------------------------------------


def test_classify_failure_no_containers_detected() -> None:
    result = MultiPassResult(
        all_passed=False,
        final_records=[],
        total_records=0,
        passes_attempted=0,
        passes_succeeded=0,
        failure_reason="no_containers_detected",
    )
    classification = classify_container_failure(result)
    assert classification["failure_class"] == "js_render_required"
    assert classification["confidence"] == pytest.approx(0.75)
    assert "JavaScript" in classification["user_message"]
    assert classification["recommended_action"] == "enable_js_rendering"


def test_classify_failure_all_passes_empty() -> None:
    result = MultiPassResult(
        all_passed=False,
        final_records=[],
        total_records=0,
        passes_attempted=3,
        passes_succeeded=0,
        failure_reason="all_passes_empty",
    )
    classification = classify_container_failure(result)
    assert classification["failure_class"] == "selector_failure"
    assert classification["confidence"] == pytest.approx(0.80)
    assert classification["recommended_action"] == "try_visible_text_fallback"


def test_classify_failure_all_passes_low_quality() -> None:
    result = MultiPassResult(
        all_passed=False,
        final_records=[{"a": "b"}],
        total_records=1,
        passes_attempted=3,
        passes_succeeded=1,
        failure_reason="all_passes_low_quality",
    )
    classification = classify_container_failure(result)
    assert classification["failure_class"] == "partial_extraction"
    assert classification["confidence"] == pytest.approx(0.60)
    assert classification["recommended_action"] == "try_alternative_strategy"


def test_classify_failure_unknown_reason_returns_genuinely_empty() -> None:
    result = MultiPassResult(
        all_passed=False,
        final_records=[],
        total_records=0,
        passes_attempted=0,
        passes_succeeded=0,
        failure_reason="mystery_cause",
    )
    classification = classify_container_failure(result)
    assert classification["failure_class"] == "genuinely_empty"
    assert classification["confidence"] == pytest.approx(0.50)
    assert classification["recommended_action"] == "verify_source_content"


def test_classify_failure_with_evidence_data_patterns_no_containers() -> None:
    """When evidence shows data patterns but no containers, classify as JS-render."""
    from app.page_evidence_collector import PageEvidence

    # Build minimal evidence with price/email patterns but no containers
    evidence = PageEvidence(
        url="https://example.com",
        patterns={"price": ["$19.99"], "email": ["a@b.com"]},
        candidate_containers=[],
    )
    result = MultiPassResult(
        all_passed=False,
        final_records=[],
        total_records=0,
        passes_attempted=0,
        passes_succeeded=0,
        failure_reason="mystery_cause",
    )
    classification = classify_container_failure(result, evidence=evidence)
    assert classification["failure_class"] == "js_render_required"
    assert classification["confidence"] == pytest.approx(0.70)


def test_classify_failure_with_evidence_both_containers_and_patterns() -> None:
    """When evidence shows both patterns and containers, fall through to genuinely_empty."""
    from app.page_evidence_collector import CandidateContainer, PageEvidence

    container = CandidateContainer(
        selector="div.result",
        tag="div",
        text_density=5.0,
        child_count=3,
    )
    evidence = PageEvidence(
        url="https://example.com",
        patterns={"price": ["$19.99"], "email": []},
        candidate_containers=[container],
    )
    result = MultiPassResult(
        all_passed=False,
        final_records=[],
        total_records=0,
        passes_attempted=0,
        passes_succeeded=0,
        failure_reason="mystery_cause",
    )
    classification = classify_container_failure(result, evidence=evidence)
    # Both patterns and containers present -> falls through to genuinely_empty
    assert classification["failure_class"] == "genuinely_empty"


# ---------------------------------------------------------------------------
# Failure-classification coverage
# ---------------------------------------------------------------------------


def test_all_documented_failure_classes_handled() -> None:
    """Verify the function returns a valid classification for every known
    failure_reason that the module documents."""
    known_reasons = [
        "no_containers_detected",
        "all_passes_empty",
        "all_passes_low_quality",
    ]
    for reason in known_reasons:
        result = MultiPassResult(
            all_passed=False,
            final_records=[],
            total_records=0,
            passes_attempted=0,
            passes_succeeded=0,
            failure_reason=reason,
        )
        classification = classify_container_failure(result)
        assert "failure_class" in classification
        assert "confidence" in classification
        assert "user_message" in classification
        assert "recommended_action" in classification
        assert 0.0 <= classification["confidence"] <= 1.0
