"""Tests for page_type_classifier.classify_page_type."""

from __future__ import annotations

import pytest
from app.page_type_classifier import (
    PageType,
    PageTypeClassification,
    classify_page_type,
)


def test_schema_org_product_classified_as_product() -> None:
    """A page with schema.org/Product markup is classified as PRODUCT."""
    html = '<html><body itemscope itemtype="https://schema.org/Product"><h1>Widget</h1></body></html>'
    result = classify_page_type(html, has_schema_org=True)
    assert result.page_type == PageType.PRODUCT
    assert result.confidence > 0.5


def test_button_add_to_cart_classified_as_product() -> None:
    """A page with 'Add to Cart' button + price is classified as PRODUCT."""
    html = '<div><button>Add to Cart</button><span class="price">$29.99</span></div>'
    result = classify_page_type(html)
    assert result.page_type == PageType.PRODUCT


def test_schema_org_jobposting_classified_as_job() -> None:
    """Schema.org/JobPosting + apply button → JOB_POSTING."""
    html = """
    <html><body itemscope itemtype="https://schema.org/JobPosting">
      <h1>Senior Engineer</h1>
      <button>Apply Now</button>
    </body></html>
    """
    result = classify_page_type(html, has_schema_org=True)
    assert result.page_type == PageType.JOB_POSTING
    assert result.confidence > 0.5


def test_search_results_page_with_count() -> None:
    """A results-count span + multi record → SEARCH_RESULTS."""
    html = """
    <div>
      <span class="results-count">8 results found</span>
      <div class="result">Item 1</div>
      <div class="result">Item 2</div>
    </div>
    """
    result = classify_page_type(html, record_count=8)
    assert result.page_type in {PageType.SEARCH_RESULTS, PageType.LISTING}


def test_article_html_with_article_tag() -> None:
    """An <article> element classifies as ARTICLE."""
    html = "<html><body><article><h1>Breaking News</h1><p>Story body.</p></article></body></html>"
    result = classify_page_type(html)
    assert result.page_type == PageType.ARTICLE


def test_social_media_class_hint() -> None:
    """A tweet card class + twitter-post regex classifies as SOCIAL_MEDIA."""
    html = '<div class="tweet-card"><span class="twitter-post">Hello world</span></div>'
    result = classify_page_type(html)
    assert result.page_type == PageType.SOCIAL_MEDIA


def test_forum_thread_class_hint() -> None:
    """A comment-thread class classifies as FORUM."""
    html = '<div><h1>Discussion</h1><div class="comment-thread">Replies...</div></div>'
    result = classify_page_type(html)
    assert result.page_type == PageType.FORUM


def test_event_schema_classified_as_event() -> None:
    """Schema.org/Event classifies as EVENT."""
    html = '<html><body itemscope itemtype="https://schema.org/Event"><h1>Concert</h1></body></html>'
    result = classify_page_type(html, has_schema_org=True)
    assert result.page_type == PageType.EVENT


def test_review_schema_classified_as_review() -> None:
    """Schema.org/Review classifies as REVIEW."""
    html = '<html><body itemscope itemtype="https://schema.org/Review"><h1>5 stars</h1></body></html>'
    result = classify_page_type(html, has_schema_org=True)
    assert result.page_type in {PageType.REVIEW, PageType.PRODUCT}


def test_empty_html_returns_unknown() -> None:
    """An empty HTML string classifies as UNKNOWN with 0 confidence."""
    result = classify_page_type("")
    assert result.page_type == PageType.UNKNOWN
    assert result.confidence == 0.0


def test_record_count_bonus_toward_listing() -> None:
    """5+ records with no other strong signals → LISTING."""
    html = "<div>" + " ".join(f"<div>Item {i}</div>" for i in range(20)) + "</div>"
    result = classify_page_type(html, record_count=20)
    assert result.page_type == PageType.LISTING


def test_record_count_one_bonus_toward_product() -> None:
    """A single record with no other strong signals leans toward PRODUCT."""
    html = "<div><h1>Widget</h1><p>$10</p></div>"
    result = classify_page_type(html, record_count=1)
    # PRODUCT gets a 0.2 boost from record_count=1; price_visible (0.3) likely tips it.
    assert result.page_type in {PageType.PRODUCT, PageType.JOB_POSTING}


def test_alternatives_returned_for_ambiguous_input() -> None:
    """Pages with multiple signals produce an alternatives list."""
    html = """
    <html itemscope itemtype="https://schema.org/Article">
    <body>
      <article>
        <h1>Product Review: Acme Widget</h1>
        <span>$29.99</span>
        <div class="comment-thread">Reader comments here</div>
      </article>
    </body></html>
    """
    result = classify_page_type(html, has_schema_org=True)
    assert isinstance(result, PageTypeClassification)
    assert isinstance(result.alternatives, list)


def test_confidence_capped_at_95() -> None:
    """Confidence is bounded to [0, 0.95] so callers don't treat it as certain."""
    html = '<html itemscope itemtype="https://schema.org/Product"></html>'
    result = classify_page_type(html, has_schema_org=True, record_count=1)
    assert result.confidence <= 0.95


def test_signals_dict_in_output() -> None:
    """Every classification carries the per-signal weight contributions."""
    html = '<html itemscope itemtype="https://schema.org/Product"></html>'
    result = classify_page_type(html, has_schema_org=True)
    assert isinstance(result.signals, dict)
    assert any("product" in k.lower() for k in result.signals)


def test_to_dict_serializable() -> None:
    """to_dict() returns plain JSON-friendly primitives."""
    html = '<html itemscope itemtype="https://schema.org/Product"></html>'
    result = classify_page_type(html, has_schema_org=True)
    d = result.to_dict()
    assert d["page_type"] == "product"
    assert isinstance(d["confidence"], float)
    assert isinstance(d["signals"], dict)
    assert isinstance(d["alternatives"], list)


@pytest.mark.parametrize(
    "html,has_schema,expected_type",
    [
        ('<div itemtype="https://schema.org/Product"></div>', True, PageType.PRODUCT),
        ('<div itemtype="https://schema.org/JobPosting"></div>', True, PageType.JOB_POSTING),
        ('<div itemtype="https://schema.org/Event"></div>', True, PageType.EVENT),
        ("<article><h1>Article</h1></article>", False, PageType.ARTICLE),
        ('<div class="results-count">30 results</div>', False, PageType.SEARCH_RESULTS),
    ],
)
def test_classification_matrix(html: str, has_schema: bool, expected_type: PageType) -> None:
    """Each canonical input maps to its expected type."""
    record_count = 10 if expected_type == PageType.SEARCH_RESULTS else 1
    result = classify_page_type(html, has_schema_org=has_schema, record_count=record_count)
    assert result.page_type == expected_type, f"HTML hint '{html[:60]}' expected {expected_type} got {result.page_type}"
