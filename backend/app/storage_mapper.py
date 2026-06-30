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


def _json_loads(val: Any, default: str = "{}") -> Any:
    """Parse JSON from *val*, but accept already-parsed dicts/lists as-is.

    The JSON migration path (``_job_from_raw``) may leave some fields as
    native Python dicts/lists rather than JSON strings.  This helper
    avoids ``json.loads(dict)`` crashes in those cases.
    """
    if isinstance(val, (dict, list)):
        return val
    if val is None:
        return json.loads(default)
    return json.loads(val)


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
        "cost_breakdown": json.dumps(job.cost_breakdown) if getattr(job, "cost_breakdown", None) else "{}",
        "cancel_requested": job.cancel_requested,
        "created_by": job.created_by or "",
        "org_id": job.org_id or "",
        "project_id": job.project_id or "",
        "created_at": job.created_at or "",
        "completed_at": job.completed_at if job.completed_at is not None else "",
        "min_record_score": job.min_record_score if job.min_record_score is not None else 0.35,
        "acquisition_mode": getattr(job.acquisition_mode, "value", None) or str(job.acquisition_mode or "standard"),
        "location": job.location or "",
        "preferred_domain": job.preferred_domain or "",
        "source_policy": getattr(job.source_policy, "value", None) or str(job.source_policy),
        "max_per_domain": job.max_per_domain or 4,
        "origin_location": job.origin_location or "",
        "max_distance_km": job.max_distance_km,
        "pagination": job.pagination,
        "deduplicate": job.deduplicate,
        "deduplicate_field": job.deduplicate_field or "",
        "started_at": job.started_at if job.started_at is not None else "",
        "results_on_disk": job.results_on_disk,
        "results_file_path": job.results_file_path if job.results_file_path is not None else "",
        "headers": json.dumps(job.headers if hasattr(job, "headers") and job.headers is not None else {}),
        "cookies": json.dumps(job.cookies if hasattr(job, "cookies") and job.cookies is not None else {}),
        "webhook_url": job.webhook_url if hasattr(job, "webhook_url") and job.webhook_url is not None else "",
        "webhook_secret": job.webhook_secret if hasattr(job, "webhook_secret") and job.webhook_secret is not None else "",
        "webhook_delivered": bool(getattr(job, "webhook_delivered", False)),
        "webhook_delivered_at": (job.webhook_delivered_at if getattr(job, "webhook_delivered_at", None) is not None else ""),
        "fetch_strategy": job.fetch_strategy if hasattr(job, "fetch_strategy") and job.fetch_strategy is not None else "",
        "hydration_wait_ms": job.hydration_wait_ms if getattr(job, "hydration_wait_ms", None) is not None else 0,
        "scroll_attempts": job.scroll_attempts if getattr(job, "scroll_attempts", None) is not None else 0,
        "request_delay_ms": job.request_delay_ms if getattr(job, "request_delay_ms", None) is not None else 0,
        "max_concurrent_urls": job.max_concurrent_urls if getattr(job, "max_concurrent_urls", None) is not None else 4,
        "user_agent": job.user_agent if hasattr(job, "user_agent") and job.user_agent is not None else "",
        "wait_for_selector": job.wait_for_selector if getattr(job, "wait_for_selector", None) is not None else "",
        "wait_for_function": job.wait_for_function if getattr(job, "wait_for_function", None) is not None else "",
        "wait_for_timeout": job.wait_for_timeout if getattr(job, "wait_for_timeout", None) is not None else None,
        "wait_for_navigation": job.wait_for_navigation if getattr(job, "wait_for_navigation", None) is not None else None,
        "cascade_telemetry": json.dumps(
            job.cascade_telemetry if hasattr(job, "cascade_telemetry") and job.cascade_telemetry is not None else {}
        ),
        "quality_score_summary": job.quality_score_summary
        if hasattr(job, "quality_score_summary") and job.quality_score_summary is not None
        else 0.0,
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
                "urls": _json_loads(row.get("urls", "[]"), "[]"),
                "schema_fields": _json_loads(row.get("schema_fields", "[]"), "[]"),
                "filters": _json_loads(row.get("filters", "[]"), "[]"),
                "results": _json_loads(row.get("results", "[]"), "[]"),
                "logs": _json_loads(row.get("logs", "[]"), "[]"),
                "total_records": row.get("total_records", 0),
                "filtered_records": row.get("filtered_records", 0),
                "total_llm_calls": row.get("total_llm_calls", 0),
                "error": row.get("error") or None,
                "quality_report": _json_loads(row.get("quality_report", "{}")),
                "analysis": row.get("analysis") or None,
                "discovered_urls": _json_loads(row.get("discovered_urls", "[]"), "[]"),
                "selectors_map": _json_loads(row.get("selectors_map", "{}")),
                "search_params": _json_loads(row.get("search_params", "{}")) or None,
                "max_pages": row.get("max_pages", 0),
                "progress_current": row.get("progress_current", 0),
                "progress_total": row.get("progress_total", 0),
                "estimated_cost_usd": row.get("estimated_cost_usd", 0),
                "cost_breakdown": _json_loads(row.get("cost_breakdown", "{}")),
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
                "warnings": _json_loads(row.get("warnings", "[]"), "[]"),
                "acquisition_mode": row.get("acquisition_mode", "standard"),
                "headers": _json_loads(row.get("headers", "{}")),
                "cookies": _json_loads(row.get("cookies", "{}")),
                "webhook_url": row.get("webhook_url") or None,
                "webhook_secret": row.get("webhook_secret") or None,
                "webhook_delivered": bool(row.get("webhook_delivered", False)),
                "webhook_delivered_at": row.get("webhook_delivered_at") or None,
                "fetch_strategy": row.get("fetch_strategy") or "",
                # hydration_wait_ms and scroll_attempts default to None when
                # not persisted — the platform falls back to its defaults.
                "hydration_wait_ms": row.get("hydration_wait_ms") or None,
                "scroll_attempts": row.get("scroll_attempts") or None,
                "request_delay_ms": row.get("request_delay_ms", 0),
                "max_concurrent_urls": row.get("max_concurrent_urls") or 4,
                "user_agent": row.get("user_agent", ""),
                "wait_for_selector": row.get("wait_for_selector") or None,
                "wait_for_function": row.get("wait_for_function") or None,
                "wait_for_timeout": row.get("wait_for_timeout") or None,
                "wait_for_navigation": bool(row.get("wait_for_navigation"))
                if row.get("wait_for_navigation") is not None
                else None,
                "cascade_telemetry": _json_loads(row.get("cascade_telemetry", "{}")),
                "quality_score_summary": row.get("quality_score_summary", 0.0),
            },
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to deserialize job row: %s", e)
        return None
