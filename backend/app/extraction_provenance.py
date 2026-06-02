"""
Extraction Provenance — Field-level explainability for extraction.

Tracks the provenance of each extracted field value:
  - How was it extracted? (selector, LLM, regex, fallback)
  - What CSS selector was used?
  - What was the extraction confidence?
  - Was it transformed or cleaned by AI?
  - What was the source HTML snippet?

This enables:
  1. Explainable extraction: users can see exactly how each value was obtained.
  2. Debugging: identify which extraction paths fail silently.
  3. Quality analysis: correlate extraction method with downstream accuracy.
  4. Commercial value: auditable extraction trails for compliance.

LAW: Every extracted field must carry provenance metadata. Without provenance,
extraction quality cannot be diagnosed or improved.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Provenance Data Model
# ═══════════════════════════════════════════════════════════════════════


class ExtractionMethod:
    """Canonical names for extraction methods used in provenance tracking."""

    PROFILE = "profile"
    MEMORY = "memory"
    DISCOVERY = "discovery"
    LLM_DISCOVERY = "llm_discovery"
    REGEX = "regex"
    LLM_CLEAN = "llm_clean"
    CONTACT_BOOST = "contact_boost"
    PIPELINE = "pipeline"
    MANUAL = "manual"
    FALLBACK = "fallback"


@dataclass
class FieldProvenance:
    """Provenance of a single extracted field value.

    Attributes:
        field_name: Name of the field (e.g., "company_name").
        value: The extracted value (or None if not found).
        method: ExtractionMethod used (e.g., "discovery", "memory", "regex").
        selector: The CSS selector used (or None if regex / LLM).
        confidence: Confidence score for this field [0, 1].
        transformed: Whether AI cleaning transformed this value.
        source_snippet: Truncated HTML snippet that was the extraction source.
        extraction_time_ms: Milliseconds for this field's extraction.
        llm_hint: The hint provided to LLM for extraction (if applicable).
        fallback_chain: Ordered list of methods tried before success.
    """

    field_name: str = ""
    value: Any = None
    method: str = "unknown"
    selector: Optional[str] = None
    confidence: float = 0.0
    transformed: bool = False
    source_snippet: Optional[str] = None
    extraction_time_ms: float = 0.0
    llm_hint: Optional[str] = None
    fallback_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        # Truncate source snippet for serialization
        if result.get("source_snippet") and len(result["source_snippet"]) > 200:
            result["source_snippet"] = result["source_snippet"][:200] + "..."
        return result


@dataclass
class ExtractionProvenance:
    """Complete provenance record for one extraction attempt (one URL).

    Tracks the full extraction chain for every field, including metadata
    about the overall extraction context.

    Attributes:
        url: The URL that was scraped.
        domain: The domain extracted from the URL.
        timestamp: When the extraction occurred.
        total_extraction_time_ms: Total time for this extraction.
        extraction_method: The primary method that produced the best results.
        records_count: Number of records extracted.
        fields: Dict of field_name -> FieldProvenance for each record.
                 Keyed by record index and field name.
        memory_hit: Whether selector memory was used.
        fallback_path: The ordered extraction cascade that was attempted.
        errors: Any errors encountered during extraction.
    """

    url: str = ""
    domain: str = ""
    timestamp: float = field(default_factory=time.time)
    total_extraction_time_ms: float = 0.0
    extraction_method: str = "unknown"
    records_count: int = 0
    fields: dict[str, FieldProvenance] = field(default_factory=dict)
    memory_hit: bool = False
    fallback_path: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["fields"] = {k: v.to_dict() if isinstance(v, FieldProvenance) else v for k, v in result["fields"].items()}
        return result


# ═══════════════════════════════════════════════════════════════════════
# Provenance Builder
# ═══════════════════════════════════════════════════════════════════════


class ProvenanceBuilder:
    """Builds extraction provenance records progressively.

    Usage:
        builder = ProvenanceBuilder(url, domain)
        builder.set_extraction_method("memory")
        builder.add_field_provenance("company_name", value, selector="div.name", method="memory")
        builder.set_records_count(10)
        provenance = builder.build()
    """

    def __init__(self, url: str, domain: str = ""):
        self._url = url
        self._domain = domain or self._extract_domain(url)
        self._start_time = time.time()
        self._extraction_method: str = "unknown"
        self._records_count: int = 0
        self._fields: dict[str, FieldProvenance] = {}
        self._memory_hit: bool = False
        self._fallback_path: list[str] = []
        self._errors: list[str] = []

    def set_extraction_method(self, method: str) -> None:
        self._extraction_method = method

    def set_records_count(self, count: int) -> None:
        self._records_count = count

    def set_memory_hit(self, hit: bool) -> None:
        self._memory_hit = hit

    def add_fallback_step(self, step: str) -> None:
        if step not in self._fallback_path:
            self._fallback_path.append(step)

    def add_error(self, error: str) -> None:
        self._errors.append(error)

    def add_field_provenance(
        self,
        record_idx: int,
        field_name: str,
        value: Any,
        method: str = "unknown",
        selector: Optional[str] = None,
        confidence: float = 0.0,
        transformed: bool = False,
        source_snippet: Optional[str] = None,
        extraction_time_ms: float = 0.0,
        llm_hint: Optional[str] = None,
        fallback_chain: Optional[list[str]] = None,
    ) -> None:
        """Add or update provenance for a single field in a record."""
        key = f"record_{record_idx}.{field_name}"
        existing = self._fields.get(key)
        if existing:
            # Update existing — append to fallback chain
            existing.fallback_chain.append(existing.method)
            existing.method = method
            existing.value = value
            existing.confidence = max(existing.confidence, confidence)
            existing.transformed = transformed or existing.transformed
            existing.selector = selector or existing.selector
            if source_snippet:
                existing.source_snippet = source_snippet
            existing.extraction_time_ms += extraction_time_ms
        else:
            self._fields[key] = FieldProvenance(
                field_name=field_name,
                value=value,
                method=method,
                selector=selector,
                confidence=confidence,
                transformed=transformed,
                source_snippet=source_snippet,
                extraction_time_ms=extraction_time_ms,
                llm_hint=llm_hint,
                fallback_chain=fallback_chain or [],
            )

    def build(self) -> ExtractionProvenance:
        """Finalize and return the provenance record."""
        return ExtractionProvenance(
            url=self._url,
            domain=self._domain,
            timestamp=self._start_time,
            total_extraction_time_ms=(time.time() - self._start_time) * 1000,
            extraction_method=self._extraction_method,
            records_count=self._records_count,
            fields=self._fields,
            memory_hit=self._memory_hit,
            fallback_path=self._fallback_path,
            errors=self._errors,
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or "unknown"
        except Exception:
            return "unknown"


# ═══════════════════════════════════════════════════════════════════════
# Provenance Enricher
# ═══════════════════════════════════════════════════════════════════════


def enrich_records_with_provenance(
    records: list[dict],
    provenance: ExtractionProvenance,
) -> list[dict]:
    """Embed provenance metadata into extracted records.

    Each record gets a ``_provenance`` dict with field-level provenance
    information. This enables downstream consumers (dashboard, export)
    to show extraction explainability.

    Args:
        records: The extracted and processed records.
        provenance: The ExtractionProvenance from this scrape.

    Returns:
        Records with ``_provenance`` metadata attached.
    """
    enriched = []
    for idx, record in enumerate(records):
        enriched_record = dict(record)

        # Build a compact provenance summary for this record
        field_provenance = {}
        for field_name in record.keys():
            if field_name.startswith("_"):
                continue
            key = f"record_{idx}.{field_name}"
            fp = provenance.fields.get(key)
            if fp:
                field_provenance[field_name] = {
                    "method": fp.method,
                    "confidence": fp.confidence,
                    "selector": fp.selector,
                    "transformed": fp.transformed,
                }

        enriched_record["_provenance"] = {
            "url": provenance.url,
            "domain": provenance.domain,
            "extraction_method": provenance.extraction_method,
            "total_time_ms": round(provenance.total_extraction_time_ms, 1),
            "memory_hit": provenance.memory_hit,
            "fallback_path": provenance.fallback_path,
            "fields": field_provenance,
        }

        enriched.append(enriched_record)

    return enriched


def summarize_provenance(provenance: ExtractionProvenance) -> dict:
    """Create a human-readable summary of the extraction provenance.

    Useful for dashboard display, export metadata, and logging.
    """
    # Count methods used
    method_counts: dict[str, int] = {}
    for fp in provenance.fields.values():
        method_counts[fp.method] = method_counts.get(fp.method, 0) + 1

    # Average confidence per method
    method_confidence: dict[str, list[float]] = {}
    for fp in provenance.fields.values():
        method_confidence.setdefault(fp.method, []).append(fp.confidence)

    avg_confidence = {method: round(sum(scores) / len(scores), 3) for method, scores in method_confidence.items()}

    # Fields with low confidence (potential issues)
    low_confidence_fields = [
        {"field": fp.field_name, "confidence": fp.confidence, "method": fp.method}
        for fp in provenance.fields.values()
        if fp.confidence < 0.5
    ]

    return {
        "url": provenance.url,
        "domain": provenance.domain,
        "extraction_method": provenance.extraction_method,
        "total_time_ms": round(provenance.total_extraction_time_ms, 1),
        "records_count": provenance.records_count,
        "method_breakdown": method_counts,
        "avg_confidence_by_method": avg_confidence,
        "memory_hit": provenance.memory_hit,
        "fallback_path": provenance.fallback_path,
        "low_confidence_fields": low_confidence_fields[:5],
        "error_count": len(provenance.errors),
    }
