"""Extraction diff / change detection.

Given two extraction result sets (each ``list[dict]`` representing one
run's records), produce a structured diff report that surfaces:

* Field-level schema drift (added/removed fields)
* Record-level additions, removals, modifications
* Overall severity classification

Used by the API layer to expose per-job change detection so operators
can spot extraction regressions before users notice.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# Field names commonly used as stable per-record identifiers across
# extractions. First match wins, then we fall back to a normalized hash.
_RECORD_KEY_CANDIDATES: tuple[str, ...] = (
    "id",
    "url",
    "sku",
    "product_id",
    "item_id",
    "name",
    "title",
)


@dataclass(frozen=True)
class ExtractionDiff:
    """Structured diff between two extraction runs on the same source.

    All fields are deterministic and serializable. ``severity`` is one of
    ``stable`` / ``minor`` / ``moderate`` / ``major``.
    """

    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    record_count_delta: int = 0
    baseline_record_count: int = 0
    current_record_count: int = 0
    added_records: list[dict[str, Any]] = field(default_factory=list)
    removed_records: list[dict[str, Any]] = field(default_factory=list)
    modified_records: list[dict[str, Any]] = field(default_factory=list)
    schema_changed: bool = False
    quality_regression: bool = False
    severity: str = "stable"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_fields": list(self.added_fields),
            "removed_fields": list(self.removed_fields),
            "record_count_delta": self.record_count_delta,
            "baseline_record_count": self.baseline_record_count,
            "current_record_count": self.current_record_count,
            "added_records": list(self.added_records),
            "removed_records": list(self.removed_records),
            "modified_records": list(self.modified_records),
            "schema_changed": self.schema_changed,
            "quality_regression": self.quality_regression,
            "severity": self.severity,
            "summary": self.summary,
        }


def _normalize_value(value: Any) -> str:
    """Coerce any scalar to a comparable string for hashing."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip().lower()
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _record_signature(record: dict[str, Any], key: str | None) -> str | None:
    """Build a stable signature for a record.

    Returns the value of the chosen ``key`` field if present, else a
    hash of all non-empty string values. Returns ``None`` for empty
    records (which the caller treats as unmatchable).
    """
    if key and key in record and record[key] not in (None, ""):
        return _normalize_value(record[key])
    for candidate in _RECORD_KEY_CANDIDATES:
        if candidate in record and record[candidate] not in (None, ""):
            return _normalize_value(record[candidate])
    payload = "|".join(f"{k}={_normalize_value(v)}" for k, v in sorted(record.items()) if v not in (None, ""))
    if not payload:
        return None
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()  # noqa: S324  # non-cryptographic, content-addressed


def _field_union(records: Iterable[dict[str, Any]]) -> set[str]:
    """Return the union of field names across records."""
    fields: set[str] = set()
    for record in records:
        fields.update(record.keys())
    return fields


def _classify_severity(
    *,
    schema_changed: bool,
    baseline_count: int,
    current_count: int,
    quality_regression: bool,
    added_count: int,
    removed_count: int,
    modified_count: int,
) -> str:
    """Ladder the diff into a coarse severity label."""
    if quality_regression or (baseline_count > 0 and current_count == 0):
        return "major"
    if schema_changed and (added_count + removed_count) > max(1, baseline_count // 2):
        return "major"
    if schema_changed or modified_count > 0:
        return "moderate"
    delta_pct = (abs(current_count - baseline_count) / baseline_count) if baseline_count else 0.0
    if delta_pct > 0.10 or (added_count + removed_count) > 0:
        return "minor"
    return "stable"


def compute_extraction_diff(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
    *,
    record_key: str | None = None,
    field_threshold: float = 0.05,
) -> ExtractionDiff:
    """Compute a structured diff between two extraction result sets.

    Args:
        baseline: Records from a previous (successful) run.
        current: Records from the latest run to compare against baseline.
        record_key: Field name used as the stable record identifier.
            When ``None``, common keys (``id`` / ``url`` / ``sku`` / ...)
            are tried in order, falling back to a content hash.
        field_threshold: Fraction of schema fields that must be
            added/removed to set ``schema_changed``. Currently only
            used as a binary threshold (any drift → True) — kept as
            a parameter so future versions can tighten it.

    Returns:
        :class:`ExtractionDiff` summarising the change.
    """
    baseline_records = [r for r in baseline if isinstance(r, dict)]
    current_records = [r for r in current if isinstance(r, dict)]

    baseline_fields = _field_union(baseline_records)
    current_fields = _field_union(current_records)
    added_fields = sorted(current_fields - baseline_fields)
    removed_fields = sorted(baseline_fields - current_fields)
    schema_changed = bool(added_fields or removed_fields)

    baseline_by_sig: dict[str, dict[str, Any]] = {}
    for record in baseline_records:
        sig = _record_signature(record, record_key)
        if sig is not None:
            baseline_by_sig.setdefault(sig, record)

    current_by_sig: dict[str, dict[str, Any]] = {}
    for record in current_records:
        sig = _record_signature(record, record_key)
        if sig is not None:
            current_by_sig.setdefault(sig, record)

    added_records = [record for sig, record in current_by_sig.items() if sig not in baseline_by_sig]
    removed_records = [record for sig, record in baseline_by_sig.items() if sig not in current_by_sig]

    modified_records: list[dict[str, Any]] = []
    for sig, current_record in current_by_sig.items():
        baseline_record = baseline_by_sig.get(sig)
        if baseline_record is None:
            continue
        if _normalize_value(baseline_record) != _normalize_value(current_record):
            modified_records.append(
                {
                    "key": sig,
                    "baseline": baseline_record,
                    "current": current_record,
                },
            )

    baseline_count = len(baseline_records)
    current_count = len(current_records)
    quality_regression = baseline_count > 0 and current_count < baseline_count * 0.5

    severity = _classify_severity(
        schema_changed=schema_changed,
        baseline_count=baseline_count,
        current_count=current_count,
        quality_regression=quality_regression,
        added_count=len(added_records),
        removed_count=len(removed_records),
        modified_count=len(modified_records),
    )

    summary = _render_summary(
        severity=severity,
        baseline_count=baseline_count,
        current_count=current_count,
        added_count=len(added_records),
        removed_count=len(removed_records),
        modified_count=len(modified_records),
        added_fields=added_fields,
        removed_fields=removed_fields,
        quality_regression=quality_regression,
    )

    return ExtractionDiff(
        added_fields=added_fields,
        removed_fields=removed_fields,
        record_count_delta=current_count - baseline_count,
        baseline_record_count=baseline_count,
        current_record_count=current_count,
        added_records=added_records,
        removed_records=removed_records,
        modified_records=modified_records,
        schema_changed=schema_changed,
        quality_regression=quality_regression,
        severity=severity,
        summary=summary,
    )


def _render_summary(
    *,
    severity: str,
    baseline_count: int,
    current_count: int,
    added_count: int,
    removed_count: int,
    modified_count: int,
    added_fields: list[str],
    removed_fields: list[str],
    quality_regression: bool,
) -> str:
    """Build a one-line human-readable summary of the diff."""
    if severity == "stable":
        return f"No meaningful change ({baseline_count} → {current_count} records)"
    bits: list[str] = [f"records {baseline_count} → {current_count}"]
    if added_count:
        bits.append(f"+{added_count} added")
    if removed_count:
        bits.append(f"-{removed_count} removed")
    if modified_count:
        bits.append(f"~{modified_count} modified")
    if added_fields:
        bits.append(f"new fields: {', '.join(added_fields)}")
    if removed_fields:
        bits.append(f"dropped fields: {', '.join(removed_fields)}")
    if quality_regression:
        bits.append("QUALITY REGRESSION")
    return f"[{severity}] " + "; ".join(bits)
