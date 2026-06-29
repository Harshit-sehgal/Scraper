"""Qual 8: Data enrichment via external APIs — test enrichment pipeline interface."""
from __future__ import annotations

from typing import Any

import pytest


def _enrich_record(record: dict, enrichment_fn: Any) -> dict:
    """Apply an enrichment function to a record.
    
    The enrichment function receives the record and returns
    a dict of new fields to merge.
    """
    new_fields = enrichment_fn(record)
    result = dict(record)
    result.update(new_fields)
    return result


def _geocode(address: str) -> dict[str, Any]:
    """Fake geocoding enrichment."""
    if not address or address == "unknown":
        return {}
    return {"latitude": 40.7128, "longitude": -74.0060, "geocoded_address": address}


def _company_lookup(domain: str) -> dict[str, Any]:
    """Fake company enrichment."""
    if not domain:
        return {}
    return {
        "company_name": f"{domain.split('.', maxsplit=1)[0].capitalize()} Inc",
        "industry": "Technology",
        "employees": "100-250",
    }


class TestEnrichmentPipeline:
    def test_geocode_enrichment_adds_coordinates(self) -> None:
        record = {"name": "Office", "address": "350 Fifth Avenue, New York, NY"}
        enriched = _enrich_record(record, lambda r: _geocode(r.get("address", "")))
        assert "latitude" in enriched
        assert "longitude" in enriched

    def test_geocode_empty_address(self) -> None:
        record = {"name": "Unknown"}
        enriched = _enrich_record(record, lambda r: _geocode(r.get("address", "")))
        assert "latitude" not in enriched

    def test_company_enrichment_adds_fields(self) -> None:
        record = {"website": "https://example.com"}
        enriched = _enrich_record(record, lambda r: _company_lookup(r.get("website", "").replace("https://", "")))
        assert enriched.get("company_name") == "Example Inc"
        assert enriched.get("industry") == "Technology"

    def test_company_enrichment_empty_domain(self) -> None:
        record = {"name": "Local Shop"}
        enriched = _enrich_record(record, lambda r: _company_lookup(""))
        assert "company_name" not in enriched

    def test_preserves_original_fields(self) -> None:
        record = {"id": 1, "title": "Product A"}
        enriched = _enrich_record(record, lambda r: {"enriched": True})
        assert enriched["id"] == 1
        assert enriched["title"] == "Product A"
        assert enriched["enriched"] is True

    def test_enrichment_overwrites_duplicate_key(self) -> None:
        record = {"title": "Original"}
        enriched = _enrich_record(record, lambda r: {"title": "Enriched"})
        assert enriched["title"] == "Enriched"


class TestEnrichmentNoOp:
    def test_empty_enrichment_funtion_no_change(self) -> None:
        record = {"a": 1, "b": 2}
        enriched = _enrich_record(record, lambda r: {})
        assert enriched == record

    def test_none_enrichment_returns_unchanged(self) -> None:
        record = {"x": "y"}
        enriched = _enrich_record(record, lambda r: {"enriched": None})
        assert enriched["enriched"] is None
        assert enriched["x"] == "y"


class TestEnrichmentPipelineErrors:
    def test_enrichment_exception_preserves_record(self) -> None:
        record = {"safe": True}

        def _broken(_r):
            msg = "Enrichment failed"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            _enrich_record(record, _broken)
