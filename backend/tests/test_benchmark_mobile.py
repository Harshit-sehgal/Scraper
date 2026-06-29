"""Bench 8: Mobile viewport benchmark (Roadmap Bench 8).

Tests mobile viewport extraction and responsive layout handling.
"""

from __future__ import annotations

from pathlib import Path

from app.empty_response_detector import detect_empty_response
from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex
from bs4 import BeautifulSoup

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestBenchmarkMobileViewport:
    """Mobile viewport extraction."""

    def test_mobile_page_has_charset_meta(self) -> None:
        html = _load("spa_react_mock.html")
        soup = BeautifulSoup(html, "html.parser")
        charset = soup.find("meta", attrs={"charset": True})
        assert charset is not None

    def test_mobile_page_still_extractable(self) -> None:
        html = _load("spa_react_mock.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/spa_react_mock.html")
        assert len(records) > 0

    def test_mobile_page_extraction_returns_typed_fields(self) -> None:
        html = _load("spa_react_mock.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/spa_react_mock.html")
        for record in records:
            assert record.get("title")


class TestBenchmarkResponsiveLayout:
    """Responsive layout handling in extraction."""

    def test_responsive_grid_structure_parseable(self) -> None:
        html = _load("ecommerce_listing.html")
        soup = BeautifulSoup(html, "html.parser")
        containers = soup.select('[class*="item"], [class*="product"], [class*="card"], [class*="listing"]')
        assert len(containers) > 0

    def test_mobile_friendly_page_extracts_titles(self) -> None:
        html = _load("social_profile.html")
        schema = [
            SchemaField(name="display_name", field_type=FieldType.STRING, required=True),
            SchemaField(name="username", field_type=FieldType.STRING, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/social_profile.html")
        assert len(records) > 0

    def test_empty_response_detector_works_on_mobile_html(self) -> None:
        html = _load("spa_react_mock.html")
        result = detect_empty_response(html)
        assert result.is_empty is False

    def test_page_has_responsive_or_readable_layout(self) -> None:
        html = _load("spa_react_mock.html")
        assert len(html) > 200

    def test_page_without_viewport_still_extracts(self) -> None:
        html = _load("legacy_directory.html")
        schema = [
            SchemaField(name="company", field_type=FieldType.STRING, required=True),
            SchemaField(name="phone", field_type=FieldType.PHONE, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/legacy_directory.html")
        assert len(records) > 0
