"""Utility modules for DataForge Scraper.

Exports:
- rbac: UserRole, require_role
- export: safe_export_filename
- job: normalize_job_results, deduplicate_results, mark_job_canceled
- quality: build_quality_report, compute_source_breakdown, safe_score, post_extract_validate_records, DedupConfig, configurable_deduplicate_records
- prod_security_validator: ProductionSecurityValidator
- job_results_store: JobResultsStore (Lazy loader to avoid circular imports at module init)
- worker_id: resolve_worker_id
"""

from app.utils.export import safe_export_filename
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
from app.utils.quality import (
    DedupConfig,
    build_quality_report,
    compute_source_breakdown,
    configurable_deduplicate_records,
    post_extract_validate_records,
    safe_score,
)
from app.utils.rbac import UserRole, require_role

__all__ = [
    "DedupConfig",
    "UserRole",
    "build_quality_report",
    "compute_source_breakdown",
    "configurable_deduplicate_records",
    "deduplicate_results",
    "mark_job_canceled",
    "normalize_job_results",
    "post_extract_validate_records",
    "require_role",
    "safe_export_filename",
    "safe_score",
]  # noqa: RUF100
