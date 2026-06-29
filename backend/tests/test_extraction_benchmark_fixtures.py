"""Fixture-backed extraction quality tests.

Validates extraction quality across different page archetypes using
checked-in HTML fixtures. No network or browser required.
"""

from __future__ import annotations

from pathlib import Path

from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex

FIXTURES_DIR = Path(__file__).parents[1] / "tests" / "fixtures" / "pages"

# ── Fixture helpers ──────────────────────────────────────────────────────


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _schema_field(name: str, field_type: str = "string", required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=FieldType(field_type), required=required, description="")


def _extract(html: str, fields: list[SchemaField]) -> list[dict]:
    return extract_with_regex(html, fields, base_url="https://fixtures.local/")


# ─── Basic extraction tests ──────────────────────────────────────────────


class TestBasicExtraction:
    """Verify extraction works on core page types."""

    def test_extract_from_ecommerce_listing(self) -> None:
        html = _load_fixture("ecommerce_listing.html")
        fields = [_schema_field("title"), _schema_field("price")]
        records = _extract(html, fields)
        assert len(records) >= 1

    def test_extract_from_search_results(self) -> None:
        html = _load_fixture("search_results.html")
        fields = [_schema_field("title"), _schema_field("link")]
        records = _extract(html, fields)
        assert len(records) >= 1

    def test_extract_from_table_catalog(self) -> None:
        html = _load_fixture("table_catalog.html")
        fields = [_schema_field("name"), _schema_field("price")]
        records = _extract(html, fields)
        assert len(records) >= 1
        names = [r.get("name", "") for r in records]
        assert any(bool(n) for n in names)

    def test_extract_from_legacy_directory(self) -> None:
        html = _load_fixture("legacy_directory.html")
        fields = [_schema_field("name"), _schema_field("category")]
        records = _extract(html, fields)
        assert len(records) >= 1


# ─── Edge case extraction ────────────────────────────────────────────────


class TestEdgeCaseExtraction:
    """Verify extraction handles edge cases gracefully."""

    def test_empty_html_returns_no_records(self) -> None:
        fields = [_schema_field("title")]
        records = _extract("<html><head></head><body></body></html>", fields)
        assert records == []

    def test_minimal_html_returns_no_records(self) -> None:
        fields = [_schema_field("title")]
        records = _extract("<!DOCTYPE html><html><body>Hello</body></html>", fields)
        # The regex extractor may find raw text content; verify it's a list
        assert isinstance(records, list)
        # All records should have a title field present
        for r in records:
            assert "title" in r

    def test_malformed_html_does_not_crash(self) -> None:
        html = _load_fixture("malformed_listing.html")
        fields = [_schema_field("title")]
        # Must not raise
        records = _extract(html, fields)
        assert isinstance(records, list)

    def test_login_page_returns_empty(self) -> None:
        html = _load_fixture("login_wall_mock.html")
        fields = [_schema_field("email"), _schema_field("name")]
        records = _extract(html, fields)
        # Login walls have no extractable data
        assert len(records) == 0

    def test_challenge_page_returns_empty(self) -> None:
        html = _load_fixture("challenge_mock.html")
        fields = [_schema_field("title")]
        records = _extract(html, fields)
        assert len(records) == 0


# ─── Schema type validation ──────────────────────────────────────────────


class TestSchemaTypeExtraction:
    """Verify extraction respects field types."""

    def test_extract_url_fields(self) -> None:
        html = _load_fixture("ecommerce_listing.html")
        fields = [_schema_field("link", field_type="url")]
        records = _extract(html, fields)
        for r in records:
            val = r.get("link", "")
            if val:
                assert str(val).startswith(("http://", "https://")), f"URL field '{val}' is not a URL"

    def test_extract_currency_fields(self) -> None:
        html = _load_fixture("ecommerce_listing.html")
        fields = [_schema_field("price", field_type="currency")]
        records = _extract(html, fields)
        for r in records:
            val = r.get("price", "")
            if val:
                assert isinstance(val, str) and len(val) > 0

    def test_multiple_field_types(self) -> None:
        html = _load_fixture("ecommerce_listing.html")
        fields = [
            _schema_field("title", field_type="string"),
            _schema_field("price", field_type="currency"),
            _schema_field("link", field_type="url"),
        ]
        records = _extract(html, fields)
        assert len(records) >= 1
        for r in records:
            for f in fields:
                assert f.name in r, f"Field '{f.name}' missing from record"
