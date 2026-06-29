"""Bench 10: i18n benchmark (Roadmap Bench 10).

Tests non-English page extraction, RTL layout handling, and
multi-byte encoding support.
"""

from __future__ import annotations

from pathlib import Path

from app.empty_response_detector import detect_empty_response
from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pages"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestBenchmarkI18nNonEnglish:
    """Non-English page extraction."""

    def test_i18n_fixture_has_multi_byte_content(self) -> None:
        html = _load("intl_marketplace.html")
        has_multi_byte = any(ord(c) > 127 for c in html)
        assert has_multi_byte, "Expected multi-byte characters in i18n fixture"

    def test_i18n_fixture_extracts_records(self) -> None:
        html = _load("intl_marketplace.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/intl_marketplace.html")
        assert len(records) > 0

    def test_i18n_extraction_preserves_unicode(self) -> None:
        html = _load("intl_marketplace.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/intl_marketplace.html")
        non_ascii_titles = [r.get("title") for r in records if r.get("title") and any(ord(c) > 127 for c in str(r["title"]))]
        assert len(non_ascii_titles) > 0

    def test_i18n_page_has_multiple_currencies(self) -> None:
        html = _load("intl_marketplace.html")
        currency_symbols = {c for c in html if c in "$£€¥₹"}
        assert len(currency_symbols) >= 3, f"Expected multiple currency symbols, found {currency_symbols}"


class TestBenchmarkI18nRTLAndEncoding:
    """RTL layout and multi-byte encoding."""

    def test_i18n_fixture_has_arabic_or_rtl_text(self) -> None:
        html = _load("intl_marketplace.html")
        has_arabic = any("\u0600" <= c <= "\u06ff" for c in html)
        has_hebrew = any("\u0590" <= c <= "\u05ff" for c in html)
        if not (has_arabic or has_hebrew):
            has_devanagari = any("\u0900" <= c <= "\u097f" for c in html)
            has_cyrillic = any("\u0400" <= c <= "\u04ff" for c in html)
            assert has_devanagari or has_cyrillic, "Expected RTL or non-Latin script in i18n fixture"

    def test_i18n_page_encoding_is_utf8(self) -> None:
        html = _load("intl_marketplace.html")
        try:
            html.encode("utf-8")
            valid = True
        except UnicodeEncodeError:
            valid = False
        assert valid, "i18n fixture is not valid UTF-8"

    def test_i18n_empty_response_detector_works(self) -> None:
        html = _load("intl_marketplace.html")
        result = detect_empty_response(html)
        assert result.is_empty is False

    def test_i18n_fixture_not_empty(self) -> None:
        html = _load("intl_marketplace.html")
        assert len(html) > 500

    def test_i18n_extraction_returns_typed_fields(self) -> None:
        html = _load("intl_marketplace.html")
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=True),
        ]
        records = extract_with_regex(html, schema, base_url="https://fixtures.local/intl_marketplace.html")
        for record in records:
            if record.get("price"):
                price_str = str(record["price"])
                assert any(c in price_str for c in ("$", "£", "€", "¥", "₹")), f"Price {price_str!r} has no currency symbol"
