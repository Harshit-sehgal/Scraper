# D2 — run_job Characterization & Extraction Plan

## Current State

`run_job` has already been extracted from `lifespan.py` into
`app/services/job_runner.py` as a standalone async function. The wrapper
`run_job_wrapper` in `lifespan.py` wires settings parameters. The function
is also callable from `scripts/run_worker.py` directly.

## Function Signature

```python
async def run_job(
    job_id: str,
    jobs_store: dict,
    persist_state_fn,
    max_discovery_urls: int,
    max_job_runtime_seconds: int,
    per_url_scrape_timeout_seconds: int,
    ai_structuring_timeout_seconds: int,
    insight_timeout_seconds: int,
    persist_state_single_fn=None,
    persist_state_single_critical_fn=None,
) -> None:
```

## Size & Complexity

- **Total lines:** ~380 (excluding helper functions at module level)
- **Nested functions:** 6 (`_cancel_requested_from_db`, `_persist_job_state`,
  `_safe_log`, `_mark_completed`, `_safe_warning`, `_scrape_single_url`)
- **Raised cyclomatic complexity:** Exceeds standard linting thresholds
  (currently suppressed with `noqa: C901` if present, or would need it)

## Nine Distinct Phases

| Phase | Lines | Responsibility | Extraction target |
|-------|-------|---------------|-------------------|
| 1. Init & helpers | 95-135 | Inner functions (`_cancel_requested_from_db`, `_persist_job_state`, `_add_job_log`) | Keep as helpers or extract to `_helpers.py` |
| 2. Auto-discovery | 140-210 | DuckDuckGo URL discovery, safety filtering, cancel checks | `discovery_orchestrator.py` |
| 3. URL scraping | 215-320 | Per-URL async scrape with semaphore, domain policy, recovery, cancellation | `scrape_orchestrator.py` |
| 4. Cancel watcher | 322-335 | Active polling loop for cancel_requested + DB signal | Merge into phase 3 |
| 5. AI structuring | 337-380 | Global AI cleaning + alignment with timeout | `ai_structuring_service.py` |
| 6. Post-processing | 382-410 | Filters, radius, dedup, quality report, source breakdown | `post_processing_service.py` |
| 7. AI insight | 412-445 | Insight generation with timeout | `insight_service.py` |
| 8. Cost + offload | 447-470 | Cost calc, disk offload for large results | Merge into phase 6 |
| 9. Status determination | 472-520 | COMPLETED/DEGRADED/EMPTY_RESULT classification, persistence | `status_classifier.py` |

## Existing Test Coverage

- **`test_api_regressions.py`:** 7 tests exercise `run_job` via
  `_run_job_wrapper` (source breakdown, scrape failures, contact warnings,
  logs, progress updates, cancellation)
- **`test_migration_regression.py`:** 2 tests call `run_job` directly
  (single-row persistence, migration regression)
- **`test_api_worker_integration.py`:** 1 test calls `run_job` directly
- **Total:** ~10 tests covering the main success paths

## Extraction Plan

### Phase 1: Extract inner services (target: one service per phase)

Each service gets its own file under `app/services/`:

```
app/services/
  job_runner.py          # Orchestrator — calls the services below
  discovery.py            # URL discovery (move from app/discovery.py)
  scrape_orchestrator.py  # Per-URL scraping with concurrency control
  ai_structuring.py       # AI cleaning and alignment
  post_processing.py      # Filters, dedup, radius, quality
  insight.py              # AI insight generation
  status_classifier.py    # Final status determination
```

### Phase 2: Depend on Job model, not raw dict

Replace `jobs_store: dict` with a typed `JobStore` interface so tests
can inject mock stores without patching module-level dicts.

### Phase 3: Add missing edge-case tests

- Empty URL list
- All URLs timeout
- AI structuring timeout
- All URLs blocked by domain policy
- Disk offload failure
- Cancellation during AI structuring
