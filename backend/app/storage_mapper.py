"""Canonical Job ↔ row serialization shared by both SQLite and Postgres backends.

Before ARCH-004 each backend maintained its own ``job_to_row`` / ``row_to_job``
pair, and the two implementations drifted apart (booleans stored as 0/1 in
SQLite vs native Python ``bool`` in Postgres; different handling of
``updated_at`` / ``deleted_at`` / ``search_params_json``).

This module provides the single source of truth.  Backend-specific
adjustments (e.g. ``deleted_at`` stamping, ``search_params_json``) are
handled at the call site, not in the mapper.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models import Job

logger = logging.getLogger(__name__)


def job_to_row(job: Job) -> dict[str, Any]:
    """Convert a Job model to a flat row dict.

    Returns a dict whose keys match the columns of the canonical storage
    schema.  Values use Python-native types (``bool``, ``str``, ``int``,
    ``float``, ``None``); each backend is responsible for any type
    adaptation required by its driver (e.g. SQLite's adapter converts
    ``True`` → ``1`` automatically).

    Fields that are backend-specific — ``updated_at``, ``deleted_at``,
    ``search_params_json`` — are intentionally excluded so the mapper
    stays backend-agnostic.
    """
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "mode": job.mode.value if hasattr(job.mode, "value") else str(job.mode),
        "topic": job.topic or "",
        "intent": job.intent or "",
        "urls": json.dumps(job.urls or []),
        "schema_fields": json.dumps(
            [f.model_dump() if hasattr(f, "model_dump") else f for f in (job.schema_fields or [])],
        ),
        "filters": (
            json.dumps(
                [f.model_dump() if hasattr(f, "model_dump") else f for f in (job.filters or [])],
            )
            if hasattr(job, "filters")
            else "[]"
        ),
        "results": json.dumps(job.results or []),
        "logs": json.dumps(
            [log.model_dump() if hasattr(log, "model_dump") else log for log in (job.logs or [])],
        ),
        "total_records": job.total_records or 0,
        "filtered_records": job.filtered_records or 0,
        "total_llm_calls": job.total_llm_calls or 0,
        "error": job.error if job.error is not None else "",
        "warnings": json.dumps(job.warnings or []),
        "quality_report": json.dumps(job.quality_report if hasattr(job, "quality_report") else {}),
        "analysis": job.analysis if job.analysis is not None else "",
        "discovered_urls": json.dumps(job.discovered_urls if hasattr(job, "discovered_urls") else []),
        "selectors_map": json.dumps(job.selectors_map if hasattr(job, "selectors_map") else {}),
        "search_params": json.dumps(
            job.search_params if hasattr(job, "search_params") and job.search_params is not None else {},
        ),
        "max_pages": job.max_pages if hasattr(job, "max_pages") else 0,
        "progress_current": job.progress_current or 0,
        "progress_total": job.progress_total or 0,
        "estimated_cost_usd": job.estimated_cost_usd or 0,
        "cancel_requested": job.cancel_requested,
        "created_by": job.created_by or "",
        "org_id": job.org_id or "",
        "project_id": job.project_id or "",
        "created_at": job.created_at or "",
        "completed_at": job.completed_at if job.completed_at is not None else "",
        "min_record_score": job.min_record_score if job.min_record_score is not None else 0.35,
        "acquisition_mode": (
            job.acquisition_mode.value
            if hasattr(job.acquisition_mode, "value")
            else str(job.acquisition_mode or "standard")
        ),
        "location": job.location or "",
        "preferred_domain": job.preferred_domain or "",
        "source_policy": job.source_policy.value
        if hasattr(job.source_policy, "value")
        else str(job.source_policy),
        "max_per_domain": job.max_per_domain or 4,
        "origin_location": job.origin_location or "",
        "max_distance_km": job.max_distance_km,
        "pagination": job.pagination,
        "deduplicate": job.deduplicate,
        "deduplicate_field": job.deduplicate_field or "",
        "started_at": job.started_at if job.started_at is not None else "",
        "results_on_disk": job.results_on_disk,
        "results_file_path": job.results_file_path if job.results_file_path is not None else "",
    }


def row_to_job(row: dict[str, Any]) -> Job | None:
    """Convert a flat row dict back to a Job model.

    Returns ``None`` when the row cannot be deserialised (e.g. missing
    required keys or invalid JSON in one of the text columns).
    """
    try:
        from app.models import SourcePolicy

        source_policy_str = row.get("source_policy", "all_sources")
        try:
            sp = SourcePolicy(source_policy_str)
        except (ValueError, KeyError):
            sp = SourcePolicy.ALL_SOURCES

        return Job.model_validate(
            {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "mode": row.get("mode", "manual"),
                "topic": row.get("topic", ""),
                "intent": row.get("intent", ""),
                "urls": json.loads(row.get("urls", "[]")),
                "schema_fields": json.loads(row.get("schema_fields", "[]")),
                "filters": json.loads(row.get("filters", "[]")),
                "results": json.loads(row.get("results", "[]")),
                "logs": json.loads(row.get("logs", "[]")),
                "total_records": row.get("total_records", 0),
                "filtered_records": row.get("filtered_records", 0),
                "total_llm_calls": row.get("total_llm_calls", 0),
                "error": row.get("error") or None,
                "quality_report": json.loads(row.get("quality_report", "{}")),
                "analysis": row.get("analysis") or None,
                "discovered_urls": json.loads(row.get("discovered_urls", "[]")),
                "selectors_map": json.loads(row.get("selectors_map", "{}")),
                "search_params": json.loads(row.get("search_params", "{}")) or None,
                "max_pages": row.get("max_pages", 0),
                "progress_current": row.get("progress_current", 0),
                "progress_total": row.get("progress_total", 0),
                "estimated_cost_usd": row.get("estimated_cost_usd", 0),
                "cancel_requested": bool(row.get("cancel_requested", False)),
                "created_by": row.get("created_by", "") or "",
                "org_id": row.get("org_id", "") or "",
                "project_id": row.get("project_id", "") or "",
                "created_at": row.get("created_at", ""),
                "completed_at": row.get("completed_at") or None,
                "min_record_score": row.get("min_record_score", 0.35),
                "location": row.get("location", ""),
                "preferred_domain": row.get("preferred_domain", ""),
                "source_policy": sp,
                "max_per_domain": row.get("max_per_domain", 4),
                "origin_location": row.get("origin_location", ""),
                "max_distance_km": row.get("max_distance_km"),
                "pagination": bool(row.get("pagination", False)),
                "deduplicate": bool(row.get("deduplicate", True)),
                "deduplicate_field": row.get("deduplicate_field", ""),
                "started_at": row.get("started_at") or None,
                "results_on_disk": bool(row.get("results_on_disk", False)),
                "results_file_path": row.get("results_file_path") or None,
                "warnings": json.loads(row.get("warnings", "[]")),
                "acquisition_mode": row.get("acquisition_mode", "standard"),
            },
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to deserialize job row: %s", e)
        return None
