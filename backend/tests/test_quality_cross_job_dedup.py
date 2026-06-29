"""Qual 12: Cross-job deduplication — test dedup across multiple jobs."""
from __future__ import annotations

import json
from typing import Any


def _record_fingerprint(record: dict, key_fields: list[str] | None = None) -> str:
    """Build a stable fingerprint for cross-job dedup."""
    if key_fields:
        parts = {k: str(record.get(k, "")) for k in key_fields}
    else:
        parts = {k: str(v) for k, v in sorted(record.items()) if k not in ("_job_id", "_record_id", "source_url", "scraped_at")}
    return json.dumps(parts, sort_keys=True, default=str)


def _cross_job_dedup(jobs_results: list[tuple[str, list[dict]]], key_fields: list[str] | None = None) -> dict[str, Any]:
    """Deduplicate records across multiple jobs. Returns merged results with provenance."""
    seen: dict[str, dict] = {}
    provenance: dict[str, list[str]] = {}

    for job_id, records in jobs_results:
        for record in records:
            fp = _record_fingerprint(record, key_fields)
            if fp not in seen:
                seen[fp] = dict(record)
                seen[fp]["_job_id"] = job_id
                provenance[fp] = [job_id]
            elif job_id not in provenance[fp]:
                provenance[fp].append(job_id)

    merged = list(seen.values())
    return {
        "total_unique": len(merged),
        "total_input": sum(len(r) for _, r in jobs_results),
        "duplicates_removed": sum(len(r) for _, r in jobs_results) - len(merged),
        "records": merged,
        "provenance": {fp: jobs for fp, jobs in provenance.items()},
    }


class TestRecordFingerprint:
    def test_identical_records_same_fingerprint(self) -> None:
        r1 = {"title": "Product A", "price": "$10"}
        r2 = {"title": "Product A", "price": "$10"}
        assert _record_fingerprint(r1) == _record_fingerprint(r2)

    def test_different_records_different_fingerprint(self) -> None:
        r1 = {"title": "Product A", "price": "$10"}
        r2 = {"title": "Product B", "price": "$20"}
        assert _record_fingerprint(r1) != _record_fingerprint(r2)

    def test_key_fields_respected(self) -> None:
        r1 = {"title": "Product", "price": "$10", "color": "red"}
        r2 = {"title": "Product", "price": "$10", "color": "blue"}
        assert _record_fingerprint(r1, key_fields=["title", "price"]) == _record_fingerprint(r2, key_fields=["title", "price"])

    def test_system_fields_excluded(self) -> None:
        r1 = {"title": "A", "_job_id": "job-1", "source_url": "http://a.com"}
        r2 = {"title": "A", "_job_id": "job-2", "source_url": "http://b.com"}
        assert _record_fingerprint(r1) == _record_fingerprint(r2)

    def test_empty_record(self) -> None:
        assert isinstance(_record_fingerprint({}), str)


class TestCrossJobDedup:
    def test_no_duplicates(self) -> None:
        jobs = [
            ("job-1", [{"title": "A"}, {"title": "B"}]),
            ("job-2", [{"title": "C"}, {"title": "D"}]),
        ]
        result = _cross_job_dedup(jobs)
        assert result["total_unique"] == 4
        assert result["duplicates_removed"] == 0

    def test_exact_duplicate_removed(self) -> None:
        jobs = [
            ("job-1", [{"title": "A"}]),
            ("job-2", [{"title": "A"}]),
        ]
        result = _cross_job_dedup(jobs)
        assert result["total_unique"] == 1
        assert result["duplicates_removed"] == 1

    def test_partial_overlap(self) -> None:
        jobs = [
            ("job-1", [{"title": "A"}, {"title": "B"}]),
            ("job-2", [{"title": "A"}, {"title": "C"}]),
        ]
        result = _cross_job_dedup(jobs)
        assert result["total_unique"] == 3
        assert result["duplicates_removed"] == 1

    def test_provenance_tracks_jobs(self) -> None:
        jobs = [
            ("job-1", [{"title": "Shared"}]),
            ("job-2", [{"title": "Shared"}]),
        ]
        result = _cross_job_dedup(jobs)
        fp = list(result["provenance"].keys())[0]
        assert "job-1" in result["provenance"][fp]
        assert "job-2" in result["provenance"][fp]

    def test_three_way_dedup(self) -> None:
        jobs = [
            ("job-1", [{"id": 1}, {"id": 2}]),
            ("job-2", [{"id": 2}, {"id": 3}]),
            ("job-3", [{"id": 3}, {"id": 4}]),
        ]
        result = _cross_job_dedup(jobs)
        assert result["total_unique"] == 4
        assert result["duplicates_removed"] == 2

    def test_empty_jobs(self) -> None:
        result = _cross_job_dedup([])
        assert result["total_unique"] == 0
        assert result["duplicates_removed"] == 0
