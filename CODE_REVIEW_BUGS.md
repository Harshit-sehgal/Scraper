# Code Review Bug Report

## Bug 1 — `recycle_bin_store` read without lock in `_render_basic_metrics_text`
**File:** `backend/app/routers/system.py:564`
**Severity:** HIGH
**What happens:** `len(recycle_bin_store)` is read without acquiring `_jobs_store_lock`. Other code paths (lines 259, 774) correctly acquire the lock. A concurrent mutation to `recycle_bin_store` during length check can cause `RuntimeError: dictionary changed size during iteration`.
**Fix:**
```python
# Line 564, wrap in lock:
with _jobs_store_lock:
    lines.append(_basic_metric_line("dataforge_recycle_bin_total", len(recycle_bin_store)))
```

---

## Bug 2 — `HTTPException` raised inside `run_in_threadpool` — client gets 500 instead of 400
**File:** `backend/app/routers/exports.py:362, 407`
**Severity:** HIGH
**What happens:** `_build_excel_content()` (line 347) is a synchronous function run via `run_in_threadpool` (line 432). Lines 362 and 407 raise `HTTPException(status_code=400, ...)`. When `HTTPException` is raised inside `run_in_threadpool`, it bubbles up through the threadpool executor. FastAPI's exception handler won't catch it properly — the client will see a 500 Internal Server Error instead of the intended 400.
**Fix:** Validate before entering `_build_excel_content`, or return a sentinel value and convert to `HTTPException` in the async context after `run_in_threadpool` returns.

---

## Bug 3 — Batch export loads up to 1M records per job into memory — OOM risk
**File:** `backend/app/routers/exports.py:492-498`
**Severity:** HIGH
**What happens:** `load_paginated_job_results_from_disk` is called with `limit=1_000_000`. For jobs with millions of results (exceeding the disk offload threshold of 1000), this loads ALL results into memory at once. For a batch export of 50 jobs (the max per `BatchExportRequest.job_ids`), this could be `50 × 1M = 50M` records in memory simultaneously, causing OOM.
**Fix:** Stream results in pages instead of loading all at once, or cap per-job memory usage.

---

## Bug 4 — Assigns raw string to `cached.status` bypassing enum validation
**File:** `backend/app/routers/jobs_read.py:56-57`
**Severity:** HIGH
**What happens:** `s["status"]` from `repo.list_job_summaries` returns a string (e.g., `"completed"`). The code assigns this directly to `cached.status` (a `JobStatus` enum field) without conversion. Later code that does `job.status.value` (expecting an enum attribute) will fail with `AttributeError: 'str' object has no attribute 'value'`.
**Fix:**
```python
from app.models import JobStatus
cached.status = JobStatus(s["status"])
```

---

## Bug 5 — `delete_job` has no error handling on `repo.move_to_recycle_bin`
**File:** `backend/app/routers/jobs_write.py:563`
**Severity:** HIGH
**What happens:** `await run_in_threadpool(repo.move_to_recycle_bin, job_id)` can raise any exception. If it fails, the exception propagates as an unhandled 500, but the job is still in `manager.jobs_store` (it wasn't popped yet). The user gets a 500 error, and the job state is inconsistent: in-memory it's still in `jobs_store`, in the DB it may or may not have been moved depending on where the error occurred.
**Fix:** Wrap in try/except and handle the failure case.

---

## Bug 6 — `restore_job` race condition between DB and in-memory state
**File:** `backend/app/routers/jobs_write.py:625-629`
**Severity:** MEDIUM
**What happens:** Line 625-626: `repo.restore_from_recycle_bin(job_id)` is called outside the lock. Then at line 627-629, the lock is acquired and the in-memory state is updated. Between the repo call and the in-memory update, another request could try to restore the same job, or a concurrent read could see stale state. If `restore_from_recycle_bin` succeeds but the in-memory move is skipped because `job_id` is no longer in `recycle_bin_store` (concurrent hard_delete), the DB has the job restored but in-memory doesn't — data loss.
**Fix:** Acquire the lock around both the DB call and in-memory update, or handle the case where the in-memory state doesn't match.

---

## Bug 7 — `hard_delete_job` deletes file before DB
**File:** `backend/app/routers/jobs_write.py:640-649`
**Severity:** MEDIUM
**What happens:** Line 641-645: reads `file_path` under lock, then deletes file from disk (line 644-645), then calls `repo.hard_delete` (line 647), then pops from in-memory (line 648-649). If `repo.hard_delete` fails at line 647, the file is already deleted from disk but the job remains in the recycle bin — data corruption (orphaned DB record).
**Fix:** Do the DB hard_delete first, then delete the file, and handle rollback on file deletion failure.

---

## Bug 8 — `clear_recycle_bin` deletes files before DB
**File:** `backend/app/routers/jobs_write.py:661-667`
**Severity:** MEDIUM
**What happens:** Lines 661-664 delete files from disk, then lines 665-667 delete from DB. If any `repo.hard_delete` fails at line 667, the file is already deleted but the DB record remains — orphaned DB records with no backing file.
**Fix:** Delete from DB first, then clean up files.

---

## Bug 9 — `persist_state` holds `_jobs_store_lock` during DB I/O
**File:** `backend/app/services/state.py:53-56`
**Severity:** MEDIUM
**What happens:** `persist_state` acquires `_jobs_store_lock` (line 53) and holds it while calling `prune_history_stores` (which does file I/O via `delete_job_results_from_disk`) and `repo.save_all` (which does DB I/O). This blocks ALL concurrent reads of `jobs_store` and `recycle_bin_store` for the entire duration of the disk and DB operations. In production with many concurrent API requests, this can cause request timeouts.
**Fix:** Snapshot the stores under the lock, then release the lock before doing I/O.

---

## Bug 10 — `TelegramNotifier` never closes its `AsyncClient`
**File:** `backend/app/services/notifications.py:19-21`
**Severity:** MEDIUM
**What happens:** `_get_client()` lazily creates an `httpx.AsyncClient` but there's no `async def close()` or `__aexit__` method. When the application shuts down, the HTTP connector and socket are leaked. Over time with enough restarts, this can exhaust file descriptors.
**Fix:** Add a `close()` method and call it during application shutdown (via lifespan).

---

## Bug 11 — Batch export silently skips jobs with no data
**File:** `backend/app/routers/exports.py:481-503`
**Severity:** LOW
**What happens:** Lines 481-484: if `job` is `None` (shouldn't happen after the freshness check at line 472, but the `continue` at line 484 means it silently drops the job from results). A user requesting a batch export of 5 jobs may get results for only 3 with no indication which were skipped. The `has_any_data` check at line 510 only verifies at least one job had data, not that ALL requested jobs were included.
**Fix:** Include all requested jobs in the response, even if empty, or warn about skipped jobs.

---

## Bug 12 — Multiple experimental endpoints lack RBAC authentication
**File:** `backend/app/routers/experimental.py:128-398`
**Severity:** LOW
**What happens:** The following endpoints have no authentication dependency: `system_topology`, `system_crystalline`, `export_knowledge`, `system_search`, `system_observability`, `system_domain_policy`, `acquisition_telemetry`, `system_topology_history`, `system_agency`, `system_replay_status`, `system_replay_chains`, `system_replay_events`. While the experimental router has a `verify_experimental_enabled` dependency, these endpoints expose internal system state to anyone when experimental routes are enabled.
**Fix:** Add `dependencies=[Depends(require_role([UserRole.ADMIN]))]` to these routes.
