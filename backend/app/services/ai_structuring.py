"""AI structuring service — extracted from ``job_runner.run_job``.

This module encapsulates the global AI structuring phase of the job
pipeline. It determines whether global AI structuring is needed,
applies it with timeout handling, and produces a structured report.

This is the first extraction from the ``run_job`` monolith as part
of the L1 strangler refactor. See ``docs/RUN_JOB_CHARACTERIZATION.md``
for the full extraction plan.
"""

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.llm_bridge import get_llm_call_count, reset_llm_call_count

logger = logging.getLogger(__name__)

# Type alias for the AI structuring report dict
AiStructuringReport = dict


def _should_run_global_ai_structuring(
    all_raw_results: list[dict],
    schema_fields: list,
    ai_source_prediction: dict,
    add_job_log,
) -> bool:
    """Determine whether global AI structuring should run.

    Returns True if:
    - There are raw results AND schema fields defined
    - No per-source AI structuring was applied (``sources_with_ai_structuring == 0``)
    - The extraction methods used are not structured (regex or unknown)
    """
    if not all_raw_results or not schema_fields:
        return False
    if ai_source_prediction.get("sources_with_ai_structuring", 0) > 0:
        return False

    ext_methods = {a.get("_extraction_method", "") for a in all_raw_results if isinstance(a, dict)}
    if ext_methods and "" not in ext_methods and "regex" not in ext_methods:
        add_job_log(
            "Skipping AI structuring — records extracted via structured method (not regex)",
            level="info",
        )
        return False

    return True


def _build_skipped_report(all_raw_results: list[dict], _schema_fields: list) -> AiStructuringReport:
    """Return a report indicating global AI structuring was skipped
    because per-source AI structuring was already applied."""
    return {
        "applied": False,
        "reason": "skipped_global_ai_source_level_applied",
        "input_records": len(all_raw_results) if all_raw_results else 0,
        "output_records": len(all_raw_results) if all_raw_results else 0,
        "total_chunks": 0,
        "ai_chunks": 0,
        "fallback_chunks": 0,
        "model_fallback_mode": False,
        "capped_records": 0,
        "quality_filtered_after_ai": 0,
    }


async def apply_global_ai_structuring(
    all_raw_results: list[dict],
    schema_fields: list,
    ai_source_prediction: dict,
    ai_structuring_timeout_seconds: int,
    add_job_log,
    on_llm_call,
    min_record_score: float = 0.35,
) -> tuple[list[dict], AiStructuringReport, list[str]]:
    """Apply global AI structuring to scraped records.

    This is the top-level orchestrator for the AI structuring phase.
    It:
    1. Decides whether AI structuring is needed
    2. Applies AI cleaning + alignment with a timeout
    3. Runs the semantic pipeline on the structured results
    4. Returns the (possibly modified) records, a report dict, and any warnings

    Args:
        all_raw_results: Raw scraped records to structure.
        schema_fields: Job schema fields for alignment.
        ai_source_prediction: Dict tracking per-source AI structuring stats.
        ai_structuring_timeout_seconds: Max seconds for AI structuring.
        add_job_log: Callable ``(message, level)`` to add a job log entry.
        on_llm_call: Callable to record LLM call counts (called with count).
        min_record_score: Minimum confidence score for AI-structured records.
            Passed through from ``job.min_record_score``.

    Returns:
        Tuple of (structured_records, report_dict, warnings_list).
        If AI structuring is skipped, returns original records with a
        skipped report and empty warnings.

    """
    new_warnings: list[str] = []
    report: AiStructuringReport = _build_skipped_report(all_raw_results, schema_fields)

    if not _should_run_global_ai_structuring(all_raw_results, schema_fields, ai_source_prediction, add_job_log):
        return all_raw_results, report, new_warnings

    add_job_log(
        f"Running global AI structuring on {len(all_raw_results)} records...",
        level="info",
    )
    logger.info("AI structuring %d scraped rows...", len(all_raw_results))

    try:
        from app.scraper import ai_clean_and_align_records as _ai_clean

        reset_llm_call_count()
        structured, report = await asyncio.wait_for(
            _ai_clean(
                all_raw_results,
                schema_fields,
                min_record_score=min_record_score,
            ),
            timeout=ai_structuring_timeout_seconds,
        )
        llm_calls = get_llm_call_count()
        on_llm_call(llm_calls)

        # Run the semantic pipeline on structured results
        from app.semantic_world_state import get_world_state

        with get_world_state().transaction("global_ai_structuring"):
            structured = await run_in_threadpool(
                _run_semantic_pipeline,
                structured,
                [f.name for f in schema_fields],
            )

        if report.get("capped_records", 0) > 0:
            new_warnings.append(
                "AI structuring processed a capped subset of rows; remaining rows used deterministic cleaning.",
            )
        if report.get("model_fallback_mode"):
            new_warnings.append(
                "AI structuring switched to deterministic fallback after repeated model timeouts / errors.",
            )
        add_job_log("AI structuring complete", level="info")
    except TimeoutError:
        new_warnings.append(
            f"AI structuring timed out after {ai_structuring_timeout_seconds}s; continuing with deterministic processing.",
        )
        add_job_log("AI structuring timed out, using fallback", level="warning")
        logger.warning("AI structuring timed out")
        structured = all_raw_results
        report = _build_skipped_report(all_raw_results, schema_fields)
        report["reason"] = "timeout"
    except Exception:
        logger.exception("AI structuring failed")
        new_warnings.append("AI structuring failed; continuing with deterministic processing.")
        add_job_log("AI structuring failed, using fallback", level="error")
        structured = all_raw_results
        report = _build_skipped_report(all_raw_results, schema_fields)
        report["reason"] = "failed"

    return structured, report, new_warnings


def _run_semantic_pipeline(records: list[dict], field_names: list[str]) -> list[dict]:
    """Run the semantic pipeline on structured records.

    Lazy-imported so the research-shell module is not loaded unless
    AI structuring actually runs.
    """
    from app.semantic_pipeline import run_pipeline as _run_pipeline

    return _run_pipeline(records, field_names)
