"""Shared System Globals — holds runtime job stores and limits to avoid circular imports.

The ``CONFIG`` mapping used to carry its own defaults that drifted from
``Settings``. It is now a derived view of the centralized settings object:

* :func:`config_view` returns a fresh dict built from ``app.config.settings``.
  This is the canonical way to read a runtime limit.
* :data:`CONFIG` remains a module-level dict for back-compat with any
  import that treats it as a mapping, but it is now regenerated from
  settings by :func:`rebuild_config_from_settings` and read through
  :data:`CONFIG` (which is re-built lazily).

The migration path is:

* New code should call :func:`config_view` (or read ``settings.<FIELD>``).
* :data:`CONFIG` continues to work for legacy callers, but values
  reflect the current ``Settings`` instance at read time.
"""

from __future__ import annotations

import threading
from typing import Any

jobs_store: dict[str, Any] = {}
recycle_bin_store: dict[str, Any] = {}

# Project-wide lock guarding read and write access to the module-level
# ``jobs_store`` and ``recycle_bin_store``. Code paths that read these
# stores (e.g. ``/api/system/status``) and code paths that mutate them
# (e.g. ``/api/jobs/{id}`` write routes) must acquire this lock to
# avoid ``RuntimeError: dictionary changed size during iteration`` and
# torn-read inconsistencies. The router-local ``JobStoreManager`` uses
# a separate per-router ``threading.Lock`` for its own compositions; do
# not replace that with this lock — the two guards exist at different
# scopes (router-level state mutations vs. module-level shared state
# reads).
_jobs_store_lock = threading.Lock()

# Legacy defaults kept only as a sanity floor; the authoritative values
# live on ``app.config.settings``. ``rebuild_config_from_settings`` will
# overwrite these on application startup.
CONFIG: dict[str, Any] = {
    "max_discovery_urls": 100,
    "per_url_timeout_seconds": 30,
    "max_job_runtime_seconds": 3600,
    "ai_structuring_timeout_seconds": 30,
    "insight_timeout_seconds": 30,
    "max_job_history": 100,
    "max_recycle_bin_history": 100,
}


def rebuild_config_from_settings() -> dict[str, Any]:
    """Refresh the legacy ``CONFIG`` mapping from the current ``Settings``.

    This is the one place that mutates ``CONFIG``. Callers should
    invoke this at application startup (or whenever settings change at
    runtime) so that legacy code that reads from ``CONFIG`` stays in
    sync with the canonical settings object.
    """
    # Imported lazily to avoid a circular import at module load.
    from app.config import settings

    CONFIG.clear()
    CONFIG.update(
        {
            "max_discovery_urls": settings.MAX_DISCOVERY_URLS,
            "per_url_timeout_seconds": settings.PER_URL_TIMEOUT_SECONDS,
            "max_job_runtime_seconds": settings.MAX_JOB_RUNTIME_SECONDS,
            "ai_structuring_timeout_seconds": settings.AI_STRUCTURING_TIMEOUT_SECONDS,
            "insight_timeout_seconds": settings.INSIGHT_TIMEOUT_SECONDS,
            "max_job_history": settings.MAX_JOB_HISTORY,
            "max_recycle_bin_history": settings.MAX_RECYCLE_BIN_HISTORY,
        },
    )
    return CONFIG


def config_view() -> dict[str, Any]:
    """Return a fresh dict of the runtime config from ``Settings``.

    Preferred over reading :data:`CONFIG` directly because it is always
    consistent with the current settings instance.
    """
    from app.config import settings

    return {
        "max_discovery_urls": settings.MAX_DISCOVERY_URLS,
        "per_url_timeout_seconds": settings.PER_URL_TIMEOUT_SECONDS,
        "max_job_runtime_seconds": settings.MAX_JOB_RUNTIME_SECONDS,
        "ai_structuring_timeout_seconds": settings.AI_STRUCTURING_TIMEOUT_SECONDS,
        "insight_timeout_seconds": settings.INSIGHT_TIMEOUT_SECONDS,
        "max_job_history": settings.MAX_JOB_HISTORY,
        "max_recycle_bin_history": settings.MAX_RECYCLE_BIN_HISTORY,
    }
