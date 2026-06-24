"""Extraction Precision Tests — Verifying structural pattern matching against real-world DOM fixtures.

These tests focus on the 'Regex Fallback' and 'Selector Engine' components
without requiring live network or LLM calls.
"""

from pathlib import Path
from typing import Any, cast

import pytest
from app.models import FieldType, SchemaField
from app.selector_engine import apply_selectors, extract_with_regex

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pages"


def load_fixture(name: str) -> str:
    with open(FIXTURES_DIR / name) as f:
        return f.read()


def test_travel_site_regex_extraction() -> None:
    html = load_fixture("travel_site.html")
    fields = [
        SchemaField(name="airline", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
    ]

    # Regex fallback should find the two flight cards
    results = cast("list[dict[str, Any]]", extract_with_regex(html, fields))

    assert len(results) >= 2
    # Verify content
    airlines = [r.get("airline") for r in results]
    assert "British Airways" in airlines
    assert "Air France" in airlines

    prices = [r.get("price") for r in results]
    assert "245.50" in prices or "£245.50" in prices


def test_legacy_directory_regex_extraction() -> None:
    html = load_fixture("legacy_directory.html")
    fields = [
        SchemaField(name="company", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="phone", field_type=FieldType.PHONE, description="", required=False),
        SchemaField(name="website", field_type=FieldType.URL, description="", required=False),
    ]

    results = cast("list[dict[str, Any]]", extract_with_regex(html, fields))

    assert len(results) == 3
    companies = [r.get("company") for r in results]
    assert "Acme Corp" in companies
    assert "Globex Inc" in companies

    phones = [r.get("phone") for r in results]
    assert "+1-555-0101" in phones

    urls = [r.get("website") for r in results]
    assert any("acme.example.com" in (u or "") for u in urls)


def test_messy_blog_regex_extraction() -> None:
    html = load_fixture("messy_blog.html")
    fields = [
        SchemaField(name="title", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="author", field_type=FieldType.STRING, description="", required=False),
    ]

    results = cast("list[dict[str, Any]]", extract_with_regex(html, fields))

    # Should ignore the ad banner and newsletter
    assert len(results) == 2
    titles = [r.get("title") for r in results]
    assert "Quantum Computing is Here" in titles
    assert "The Future of AI Agents" in titles


def test_rating_named_string_field_uses_rating_node() -> None:
    html = """
    <html>
      <body>
        <div class="book">
          <h2 class="title">The Great Gatsby</h2>
          <span class="price">$15.99</span>
          <span class="rating">5 stars</span>
        </div>
        <div class="book">
          <h2 class="title">To Kill a Mockingbird</h2>
          <span class="price">$12.49</span>
          <span class="rating">4 stars</span>
        </div>
      </body>
    </html>
    """
    fields = [
        SchemaField(name="title", field_type=FieldType.STRING, description="Book title", required=True),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="Book price", required=True),
        SchemaField(name="rating", field_type=FieldType.STRING, description="Star rating", required=False),
    ]

    results = cast("list[dict[str, Any]]", extract_with_regex(html, fields))

    assert [r.get("rating") for r in results] == ["5 stars", "4 stars"]


def test_quote_card_regex_extraction_uses_named_child_nodes() -> None:
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

    results = cast("list[dict[str, Any]]", extract_with_regex(html, fields))

    assert [{field: row.get(field) for field in ("text", "author")} for row in results] == [
        {"text": "Be yourself; everyone else is already taken.", "author": "Oscar Wilde"},
        {"text": "So many books, so little time.", "author": "Frank Zappa"},
    ]


@pytest.mark.parametrize(
    "fixture_name",
    [
        "login_wall_mock.html",
        "challenge_mock.html",
        "session_expired.html",
    ],
)
def test_regex_fallback_does_not_extract_access_block_pages(fixture_name: str) -> None:
    html = load_fixture(fixture_name)
    fields = [
        SchemaField(name="title", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
    ]

    assert extract_with_regex(html, fields) == []


def test_selector_application_precision() -> None:
    html = load_fixture("travel_site.html")
    fields = [
        SchemaField(name="airline", field_type=FieldType.STRING, description="", required=False),
        SchemaField(name="price", field_type=FieldType.CURRENCY, description="", required=False),
    ]

    # Simulate an LLM-generated selector map
    selectors = {"item_container": "div.flight-card", "fields": {"airline": "span.name", "price": "span.amount"}}

    results = cast("list[dict[str, Any]]", apply_selectors(html, selectors, fields))

    assert len(results) == 2
    assert results[0]["airline"] == "British Airways"
    assert results[0]["price"] == "245.50"
    assert results[1]["airline"] == "Air France"
