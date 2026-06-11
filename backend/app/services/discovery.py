"""Discovery phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates auto-discovery mode: URL discovery, safety validation,
and discovered URL assignment.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from app.llm_bridge import get_llm_call_count, reset_llm_call_count
from app.services._job_log import log_job_message as _log

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


async def run_discovery_phase(
    job: Any,
    *,
    max_discovery_urls: int,
    persist_fn: Callable,
    cancel_check: Callable[[], Any],
) -> bool:
    """Execute the auto-discovery phase for a job.

    Returns True if discovery completed successfully (URLs found).
    Returns False if the job should terminate (canceled or failed).
    """
    from app.discovery import discover_urls
    from app.models import JobStatus

    reset_llm_call_count()
    job.status = JobStatus.DISCOVERING
    job.progress_total = int(job.max_pages or 10) + 2
    job.progress_current = 1
    _log(job, f"Starting auto-discovery for topic: {job.topic}", persist_fn=persist_fn)

    discovery_limit = int(job.max_pages or 10)
    discovery_limit = max(1, min(discovery_limit, max_discovery_urls))

    discovered = await discover_urls(
        query=job.topic,
        domain=job.preferred_domain,
        num_results=discovery_limit,
        location=job.location,
        data_fields=[f.name for f in job.schema_fields],
        origin_location=job.origin_location,
        max_distance_km=job.max_distance_km,
        source_policy=job.source_policy,
        max_per_domain=job.max_per_domain,
    )
    job.total_llm_calls += get_llm_call_count()

    from app.url_safety import validate_public_http_url

    safe_discovered = []
    safe_urls = []
    for d in discovered:
        url = d.get("url")
        if url:
            try:
                validate_public_http_url(url)
                safe_discovered.append(d)
                safe_urls.append(url)
            except ValueError:
                pass
    job.discovered_urls = safe_discovered
    job.urls = safe_urls

    if not job.urls:
        if await cancel_check():
            job.cancel_requested = True
            _log(job, "Job canceled during discovery", level="warning", persist_fn=persist_fn)
            return False
        job.status = JobStatus.FAILED
        job.error = "Could not discover any URLs for this topic"
        job.completed_at = datetime.datetime.now(datetime.UTC).isoformat()
        _log(job, "Discovery failed: No URLs found", level="error", persist_fn=persist_fn)
        return False

    _log(job, f"Discovered {len(job.urls)} potential source URLs", persist_fn=persist_fn)
    job.progress_total = len(job.urls) + 2
    job.progress_current = 1
    logger.info("Discovered %d URLs", len(job.urls))

    if await cancel_check():
        job.cancel_requested = True
        _log(job, "Job canceled after discovery", level="warning", persist_fn=persist_fn)
        return False

    return True
