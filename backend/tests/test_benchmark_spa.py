"""Bench 9: SPA benchmark (Roadmap Bench 9).

Tests framework initialization wait and client-side rendered content
extraction from SPA fixture pages.
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


class TestBenchmarkSPAFrameworkInit:
    """SPA framework initialization detection."""

    def test_spa_fixture_has_app_root(self) -> None:
        html = _load("spa_react_mock.html")
        assert 'id="hydration-root"' in html or 'id="root"' in html or 'id="app"' in html

    def test_spa_fixture_has_rendered_content(self) -> None:
        html = _load("spa_react_mock.html")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        assert len(text) > 50

    def test_spa_has_data_attributes(self) -> None:
        html = _load("spa_react_mock.html")
        soup = BeautifulSoup(html, "html.parser")
        data_attrs = soup.find_all(lambda tag: any(k.startswith("data-") for k in tag.attrs))
        assert len(data_attrs) > 0


class TestBenchmarkSPAContentExtraction:
    """CSR content extraction from SPA fixtures."""

    def test_spa_react_fixture_extracts_product_data(self) -> None:
        html = _load("spa_react_mock.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/spa_react_mock.html")
        assert len(records) == 5

    def test_spa_react_extraction_returns_product_titles(self) -> None:
        html = _load("spa_react_mock.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/spa_react_mock.html")
        titles = [r.get("title") for r in records if r.get("title")]
        assert len(titles) >= 3

    def test_spa_static_fallback_works(self) -> None:
        html = _load("infinite_scroll_mock.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/infinite_scroll_mock.html")
        assert len(records) > 0

    def test_spa_empty_response_detection(self) -> None:
        html = _load("spa_react_mock.html")
        result = detect_empty_response(html)
        assert result.is_empty is False

    def test_spa_fixture_not_empty(self) -> None:
        html = _load("spa_react_mock.html")
        assert len(html) > 500
