"""
Extraction Precision Tests — Verifying structural pattern matching against real-world DOM fixtures.

These tests focus on the 'Regex Fallback' and 'Selector Engine' components
without requiring live network or LLM calls.
"""

from pathlib import Path
from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex, apply_selectors

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pages"

def load_fixture(name: str) -> str:
    with open(FIXTURES_DIR / name, "r") as f:
        return f.read()

def test_travel_site_regex_extraction():
    html = load_fixture("travel_site.html")
    fields = [
        SchemaField(name="airline", field_type=FieldType.STRING),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]
    
    # Regex fallback should find the two flight cards
    results = extract_with_regex(html, fields)
    
    assert len(results) >= 2
    # Verify content
    airlines = [r.get("airline") for r in results]
    assert "British Airways" in airlines
    assert "Air France" in airlines
    
    prices = [r.get("price") for r in results]
    assert "245.50" in prices or "£245.50" in prices

def test_legacy_directory_regex_extraction():
    html = load_fixture("legacy_directory.html")
    fields = [
        SchemaField(name="company", field_type=FieldType.STRING),
        SchemaField(name="phone", field_type=FieldType.PHONE),
        SchemaField(name="website", field_type=FieldType.URL),
    ]
    
    results = extract_with_regex(html, fields)
    
    assert len(results) == 3
    companies = [r.get("company") for r in results]
    assert "Acme Corp" in companies
    assert "Globex Inc" in companies
    
    phones = [r.get("phone") for r in results]
    assert "+1-555-0101" in phones
    
    urls = [r.get("website") for r in results]
    assert any("acme.example.com" in (u or "") for u in urls)

def test_messy_blog_regex_extraction():
    html = load_fixture("messy_blog.html")
    fields = [
        SchemaField(name="title", field_type=FieldType.STRING),
        SchemaField(name="author", field_type=FieldType.STRING),
    ]
    
    results = extract_with_regex(html, fields)
    
    # Should ignore the ad banner and newsletter
    assert len(results) == 2
    titles = [r.get("title") for r in results]
    assert "Quantum Computing is Here" in titles
    assert "The Future of AI Agents" in titles

def test_selector_application_precision():
    html = load_fixture("travel_site.html")
    fields = [
        SchemaField(name="airline", field_type=FieldType.STRING),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]
    
    # Simulate an LLM-generated selector map
    selectors = {
        "item_container": "div.flight-card",
        "fields": {
            "airline": "span.name",
            "price": "span.amount"
        }
    }
    
    results = apply_selectors(html, selectors, fields)
    
    assert len(results) == 2
    assert results[0]["airline"] == "British Airways"
    assert results[0]["price"] == "245.50"
    assert results[1]["airline"] == "Air France"
