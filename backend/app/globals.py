"""Shared System Globals — holds runtime job stores and limits to avoid circular imports."""

from typing import Any

jobs_store: dict[str, Any] = {}
recycle_bin_store: dict[str, Any] = {}

CONFIG: dict[str, Any] = {
    "max_discovery_urls": 100,
    "per_url_timeout_seconds": 30,
    "max_job_runtime_seconds": 3600,
    "ai_structuring_timeout_seconds": 30,
    "insight_timeout_seconds": 30,
    "max_job_history": 100,
    "max_recycle_bin_history": 100,
}
