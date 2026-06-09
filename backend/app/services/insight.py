"""AI insight phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates AI insight generation over final results.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.llm_bridge import get_llm_call_count, reset_llm_call_count
from app.services._job_log import log_job_message as _log

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


async def run_insight_phase(
    job: Any,
    *,
    insight_timeout_seconds: int,
    persist_fn: Callable,
    cancel_check: Callable[[], Any],
) -> None:
    """Generate AI insights for the job's final results.

    Skips if results are empty or cancel is requested.
    """
    if not job.results:
        return

    if await cancel_check():
        job.cancel_requested = True
        _log(job, "Job canceled before AI insight", level="warning", persist_fn=persist_fn)
        return

    from app.models import JobStatus

    job.status = JobStatus.RUNNING
    _log(job, f"Generating AI insights for {len(job.results)} records...", persist_fn=persist_fn)
    logger.info("Generating AI insights over %d records...", len(job.results))
    try:
        from app.insight_engine import generate_data_insight

        reset_llm_call_count()
        analysis_text = await asyncio.wait_for(
            generate_data_insight(job.results),
            timeout=insight_timeout_seconds,
        )
        job.total_llm_calls += get_llm_call_count()
        job.analysis = analysis_text
        _log(job, "AI insights generated successfully")
    except TimeoutError:
        job.total_llm_calls += get_llm_call_count()
        _log(job, "AI insight generation timed out", level="warning")
        logger.warning("AI insight timed out after %ds", insight_timeout_seconds)
        job.analysis = "Insight generation timed out."
    except Exception:
        job.total_llm_calls += get_llm_call_count()
        logger.exception("AI insight generation failed")
        _log(job, "AI insight generation failed", level="error")
