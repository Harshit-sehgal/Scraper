"""
Tests for Extraction Provenance — Field-level explainability for extraction.

Tests cover:
  - FieldProvenance creation and serialization
  - ExtractionProvenance creation and serialization
  - ProvenanceBuilder: building, adding fields, fallback chains
  - enrich_records_with_provenance: provenance metadata embedding
  - summarize_provenance: summary statistics and low-confidence detection
"""

from __future__ import annotations

import pytest
from app.extraction_provenance import (
    ExtractionMethod,
    ExtractionProvenance,
    FieldProvenance,
    ProvenanceBuilder,
    enrich_records_with_provenance,
    summarize_provenance,
)

# ═══════════════════════════════════════════════════════════════════════
# FieldProvenance Tests
# ═══════════════════════════════════════════════════════════════════════


class TestFieldProvenance:
    def test_default_construction(self):
        fp = FieldProvenance()
        assert fp.field_name == ""
        assert fp.value is None
        assert fp.method == "unknown"
        assert fp.selector is None
        assert fp.confidence == 0.0
        assert fp.transformed is False
        assert fp.fallback_chain == []

    def test_construction_with_values(self):
        fp = FieldProvenance(
            field_name="company_name",
            value="Acme Corp",
            method=ExtractionMethod.DISCOVERY,
            selector="div.name",
            confidence=0.95,
            transformed=True,
            source_snippet="<div class='name'>Acme Corp</div>",
            extraction_time_ms=45.2,
            llm_hint="Find company name",
            fallback_chain=["memory", "regex"],
        )
        assert fp.field_name == "company_name"
        assert fp.value == "Acme Corp"
        assert fp.method == "discovery"
        assert fp.selector == "div.name"
        assert fp.confidence == 0.95
        assert fp.transformed is True
        assert fp.extraction_time_ms == 45.2
        assert fp.fallback_chain == ["memory", "regex"]

    def test_to_dict(self):
        fp = FieldProvenance(
            field_name="email",
            value="test@example.com",
            method=ExtractionMethod.REGEX,
            confidence=0.65,
        )
        d = fp.to_dict()
        assert d["field_name"] == "email"
        assert d["method"] == "regex"
        assert d["confidence"] == 0.65
        assert d["transformed"] is False
        assert d["source_snippet"] is None

    def test_to_dict_truncates_long_snippet(self):
        long_snippet = "x" * 500
        fp = FieldProvenance(
            field_name="desc",
            value="long",
            method="discovery",
            source_snippet=long_snippet,
        )
        d = fp.to_dict()
        assert len(d["source_snippet"]) <= 203  # 200 + "..."


# ═══════════════════════════════════════════════════════════════════════
# ExtractionProvenance Tests
# ═══════════════════════════════════════════════════════════════════════


class TestExtractionProvenance:
    def test_default_construction(self):
        ep = ExtractionProvenance()
        assert ep.url == ""
        assert ep.domain == ""
        assert ep.extraction_method == "unknown"
        assert ep.records_count == 0
        assert ep.memory_hit is False
        assert ep.fields == {}
        assert ep.errors == []

    def test_construction_with_values(self):
        fp = FieldProvenance(field_name="name", value="Acme", method="discovery", confidence=0.9)
        ep = ExtractionProvenance(
            url="https://example.com/page",
            domain="example.com",
            extraction_method="discovery",
            records_count=5,
            fields={"record_0.name": fp},
            memory_hit=False,
            fallback_path=["memory", "regex"],
            errors=["memory failed"],
        )
        assert ep.url == "https://example.com/page"
        assert ep.domain == "example.com"
        assert ep.extraction_method == "discovery"
        assert ep.records_count == 5
        assert ep.memory_hit is False
        assert ep.fallback_path == ["memory", "regex"]
        assert ep.errors == ["memory failed"]

    def test_to_dict(self):
        fp = FieldProvenance(field_name="name", value="Acme", method="discovery", confidence=0.9)
        ep = ExtractionProvenance(
            url="https://example.com",
            domain="example.com",
            extraction_method="memory",
            records_count=2,
            fields={"record_0.name": fp},
        )
        d = ep.to_dict()
        assert d["url"] == "https://example.com"
        assert d["extraction_method"] == "memory"
        assert "fields" in d
        assert d["fields"]["record_0.name"]["field_name"] == "name"
        assert d["fields"]["record_0.name"]["confidence"] == 0.9


# ═══════════════════════════════════════════════════════════════════════
# ProvenanceBuilder Tests
# ═══════════════════════════════════════════════════════════════════════


class TestProvenanceBuilder:
    def test_build_empty(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        ep = builder.build()
        assert ep.url == "https://example.com"
        assert ep.domain == "example.com"
        assert ep.extraction_method == "unknown"
        assert ep.records_count == 0
        assert ep.fields == {}
        assert ep.total_extraction_time_ms >= 0

    def test_domain_auto_extraction(self):
        builder = ProvenanceBuilder("https://example.com/page?q=test#section")
        ep = builder.build()
        assert ep.domain == "example.com"

    def test_set_extraction_method(self):
        builder = ProvenanceBuilder("https://example.com")
        builder.set_extraction_method(ExtractionMethod.DISCOVERY)
        assert builder.build().extraction_method == "discovery"

    def test_set_records_count(self):
        builder = ProvenanceBuilder("https://example.com")
        builder.set_records_count(42)
        assert builder.build().records_count == 42

    def test_set_memory_hit(self):
        builder = ProvenanceBuilder("https://example.com")
        builder.set_memory_hit(True)
        assert builder.build().memory_hit is True

    def test_add_fallback_step(self):
        builder = ProvenanceBuilder("https://example.com")
        builder.add_fallback_step("memory")
        builder.add_fallback_step("regex")
        assert builder.build().fallback_path == ["memory", "regex"]

    def test_add_fallback_step_deduplicates(self):
        builder = ProvenanceBuilder("https://example.com")
        builder.add_fallback_step("memory")
        builder.add_fallback_step("memory")
        assert builder.build().fallback_path == ["memory"]

    def test_add_error(self):
        builder = ProvenanceBuilder("https://example.com")
        builder.add_error("Something went wrong")
        assert builder.build().errors == ["Something went wrong"]

    def test_add_field_provenance_creates_entry(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.add_field_provenance(
            record_idx=0,
            field_name="name",
            value="Acme Corp",
            method=ExtractionMethod.DISCOVERY,
            selector="div.name",
            confidence=0.95,
            transformed=False,
            source_snippet="<div>Acme Corp</div>",
            extraction_time_ms=12.3,
            llm_hint="Find company",
        )
        ep = builder.build()
        key = "record_0.name"
        assert key in ep.fields
        fp = ep.fields[key]
        assert fp.field_name == "name"
        assert fp.value == "Acme Corp"
        assert fp.method == "discovery"
        assert fp.confidence == 0.95
        assert fp.extraction_time_ms == 12.3

    def test_add_field_provenance_updates_existing(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.add_field_provenance(
            record_idx=0,
            field_name="name",
            value="Acme Corp",
            method=ExtractionMethod.REGEX,
            confidence=0.5,
        )
        # Update with better method
        builder.add_field_provenance(
            record_idx=0,
            field_name="name",
            value="Acme Incorporated",
            method=ExtractionMethod.DISCOVERY,
            confidence=0.95,
        )
        ep = builder.build()
        fp = ep.fields["record_0.name"]
        # Should have the better value and method
        assert fp.value == "Acme Incorporated"
        assert fp.method == "discovery"
        assert fp.confidence == 0.95
        # Should have recorded the fallback chain
        assert "regex" in fp.fallback_chain

    def test_multiple_records_and_fields(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        for idx in range(3):
            builder.add_field_provenance(idx, "name", f"Company {idx}", "discovery", confidence=0.9)
            builder.add_field_provenance(idx, "email", f"info@{idx}.com", "regex", confidence=0.7)
        ep = builder.build()
        assert len(ep.fields) == 6  # 3 records x 2 fields
        assert "record_0.name" in ep.fields
        assert "record_2.email" in ep.fields
        assert ep.fields["record_1.email"].value == "info@1.com"


# ═══════════════════════════════════════════════════════════════════════
# enrich_records_with_provenance Tests
# ═══════════════════════════════════════════════════════════════════════


class TestEnrichRecordsWithProvenance:
    def test_enriches_records_with_provenance_metadata(self):
        records = [
            {"company_name": "Acme Corp", "email": "acme@example.com"},
        ]
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.set_extraction_method("discovery")
        builder.add_field_provenance(0, "company_name", "Acme Corp", "discovery", confidence=0.95)
        builder.add_field_provenance(0, "email", "acme@example.com", "regex", confidence=0.80)
        provenance = builder.build()

        enriched = enrich_records_with_provenance(records, provenance)
        assert len(enriched) == 1
        assert "_provenance" in enriched[0]
        meta = enriched[0]["_provenance"]
        assert meta["url"] == "https://example.com"
        assert meta["extraction_method"] == "discovery"
        assert meta["memory_hit"] is False
        assert "fields" in meta
        assert "company_name" in meta["fields"]
        assert meta["fields"]["company_name"]["method"] == "discovery"
        assert meta["fields"]["company_name"]["confidence"] == 0.95

    def test_enrich_multiple_records(self):
        records = [
            {"company_name": "Alpha"},
            {"company_name": "Beta"},
        ]
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.set_extraction_method("memory")
        builder.set_memory_hit(True)
        for idx in range(2):
            builder.add_field_provenance(idx, "company_name", f"Company {idx}", "memory", confidence=0.85)
        provenance = builder.build()

        enriched = enrich_records_with_provenance(records, provenance)
        assert len(enriched) == 2
        for record in enriched:
            assert record["_provenance"]["memory_hit"] is True
            assert record["_provenance"]["extraction_method"] == "memory"

    def test_enrich_skips_internal_fields(self):
        records = [
            {"company_name": "Acme", "_score": 0.9, "_id": "abc123"},
        ]
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.set_extraction_method("regex")
        builder.add_field_provenance(0, "company_name", "Acme", "regex", confidence=0.7)
        provenance = builder.build()

        enriched = enrich_records_with_provenance(records, provenance)
        meta = enriched[0]["_provenance"]["fields"]
        assert "company_name" in meta
        assert "_score" not in meta
        assert "_id" not in meta


# ═══════════════════════════════════════════════════════════════════════
# summarize_provenance Tests
# ═══════════════════════════════════════════════════════════════════════


class TestSummarizeProvenance:
    def test_summarize_empty(self):
        provenance = ExtractionProvenance(url="https://example.com", domain="example.com")
        summary = summarize_provenance(provenance)
        assert summary["url"] == "https://example.com"
        assert summary["records_count"] == 0
        assert summary["method_breakdown"] == {}

    def test_summarize_with_fields(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.set_extraction_method(ExtractionMethod.DISCOVERY)
        builder.set_records_count(2)
        builder.add_field_provenance(0, "name", "Acme", ExtractionMethod.DISCOVERY, confidence=0.95)
        builder.add_field_provenance(0, "email", "a@b.com", ExtractionMethod.REGEX, confidence=0.70)
        builder.add_field_provenance(1, "name", "Beta", ExtractionMethod.DISCOVERY, confidence=0.90)
        builder.add_field_provenance(1, "email", "b@c.com", ExtractionMethod.REGEX, confidence=0.65)
        provenance = builder.build()

        summary = summarize_provenance(provenance)
        assert summary["method_breakdown"] == {"discovery": 2, "regex": 2}
        assert summary["avg_confidence_by_method"]["discovery"] == pytest.approx(0.925, 0.01)
        assert summary["avg_confidence_by_method"]["regex"] == pytest.approx(0.675, 0.01)
        assert summary["error_count"] == 0

    def test_summarize_low_confidence_fields(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.add_field_provenance(0, "name", "Acme", "discovery", confidence=0.95)
        builder.add_field_provenance(0, "email", "a@b.com", "regex", confidence=0.30)
        provenance = builder.build()

        summary = summarize_provenance(provenance)
        assert len(summary["low_confidence_fields"]) == 1
        assert summary["low_confidence_fields"][0]["field"] == "email"
        assert summary["low_confidence_fields"][0]["confidence"] == 0.30

    def test_summarize_fallback_path(self):
        builder = ProvenanceBuilder("https://example.com", "example.com")
        builder.add_fallback_step("memory")
        builder.add_fallback_step("discovery")
        provenance = builder.build()

        summary = summarize_provenance(provenance)
        assert summary["fallback_path"] == ["memory", "discovery"]
