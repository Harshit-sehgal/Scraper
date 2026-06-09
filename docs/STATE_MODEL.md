# State Model — In-Memory Cache vs Persistent Store

## Problem

DataForge maintains two independent stores for job state: a fast
in-memory dict (`manager.jobs_store`) and a persistent database
(SQLite or Postgres). In production with Postgres, the relationship
between these two stores must be explicit so operators and developers
can reason about consistency, durability, and recovery.

## Current architecture (as of June 2026)

```
┌──────────────────────┐       ┌─────────────────────────┐
│   API Router         │       │   Worker / Background    │
│   (FastAPI handler)  │       │   (job execution)        │
└──────────┬───────────┘       └──────────┬────────────────┘
           │ Read/write                    │ Read/write
           ▼                               ▼
┌──────────────────────┐       ┌─────────────────────────┐
│  manager.jobs_store  │       │  manager.jobs_store      │
│  (in-memory dict)    │◄──────│  (in-memory dict)        │
└──────────┬───────────┘       └──────────┬────────────────┘
           │                              │
           │ Background persist           │ Direct persist
           ▼                              ▼
┌──────────────────────┐       ┌─────────────────────────┐
│  JobRepository       │       │  JobRepository           │
│  (SQLite / Postgres) │       │  (SQLite / Postgres)     │
└──────────────────────┘       └─────────────────────────┘
```

### Current source-of-truth rules

1. **In-memory dict is the primary source of truth** for all API
   responses. The API responds from `manager.jobs_store` without
   consulting the database first.

2. **The persistent store is a recovery record.** On restart,
   `load_state()` reads from the database and repopulates the
   in-memory dict. During normal operation, the database is updated
   via background persistence (`save_state`) and per-mutation
   single-row writes (`persist_state_single`, `move_to_recycle_bin`,
   `hard_delete`).

3. **Lock release between in-memory and DB writes.** Mutation
   handlers deliberately release `manager.lock` between the
   in-memory update and the DB call to avoid holding a sync lock
   across `await`. The documented trade-off is:
   > "if the DB move fails after the in-memory pop, the in-memory
   > store is consistent (job is gone) but the persistent store is
   > not (job is still active). Callers therefore MUST treat the
   > in-memory store as the source of truth."

4. **Worker reads go through the repository directly.** The worker
   mode (`DATAFORGE_WORKER_QUEUE=true`) uses `get_job()` /
   `save_single()` on the repository for cross-process state
   visibility, bypassing `manager.jobs_store` for reads.

## Ideal production state model

```
┌──────────────────────┐       ┌─────────────────────────┐
│   API Router         │       │   Worker / Background    │
│   (FastAPI handler)  │       │   (job execution)        │
└──────────┬───────────┘       └──────────┬────────────────┘
           │                               │
           ▼                               ▼
┌──────────────────────┐       ┌─────────────────────────┐
│  manager.jobs_store  │       │  manager.jobs_store      │
│  (READ-THROUGH cache)│       │  (READ-THROUGH cache)    │
│                      │       │                          │
│  All writes:         │       │  All writes:             │
│  DB first, then      │       │  DB first, then          │
│  invalidate/update   │       │  invalidate/update       │
│  local cache         │       │  local cache             │
└──────────┬───────────┘       └──────────┬────────────────┘
           │                               │
           │ DB is SOT                     │ DB is SOT
           ▼                               ▼
┌──────────────────────┐       ┌─────────────────────────┐
│  Postgres            │       │  Postgres               │
│  (source of truth)   │       │  (source of truth)      │
└──────────────────────┘       └─────────────────────────┘
```

In this model:

- **Postgres is the sole source of truth.** Every API read goes
  through the repository and caches results in the in-memory dict
  (read-through cache pattern).
- **Writes go to Postgres first.** After the DB write succeeds,
  the in-memory cache is invalidated or updated. This ensures
  that a partial-process restart or crash does not lose state.
- **The lock-across-await trade-off is eliminated.** Since the DB
  write completes before the in-memory dict is updated, there is
  no window where the two stores diverge.

## Gap analysis

| Aspect | Current | Ideal | Impact |
|--------|---------|-------|--------|
| Source of truth | In-memory dict | Postgres | After restart, in-flight mutations between the last `save_state` and a crash are lost. Acceptable for single-instance dev; risky for production with auto-scaling workers. |
| Read path | In-memory dict only | DB first, cache second | Current approach is fast but can serve stale data when another process updates the DB. |
| Write order | In-memory first, DB second | DB first, cache second | Current approach means the in-memory store can be ahead of the DB. On crash, the DB has stale data. |
| Consistency guarantee | Eventual (background persist) | Immediate (per-mutation) | Current approach is eventually consistent within a few seconds. |

## When each store is authoritative

| Scenario | Source of truth | Rationale |
|----------|---------------|-----------|
| `GET /api/jobs` (single-instance API) | In-memory | Fastest path; single process means no divergence |
| `GET /api/jobs` (worker queue mode) | Repository (DB) | Cross-process reads must reflect other workers' writes |
| `POST /api/jobs` (create) | In-memory first, DB persisted | `save_job()` called immediately after creation |
| `POST /api/jobs/{id}/cancel` | In-memory + DB | Both updated; `is_cancel_requested()` reads from DB for cross-process |
| `DELETE /api/jobs/{id}` | DB first (move_to_recycle_bin), then in-memory pop | Documented lock-release trade-off |
| Restart / recovery | DB | `load_state()` reads from DB and repopulates in-memory dict |
| `/ready` health check | DB | `health_check()` reads from repository |
| Dashboard status counts | DB | `count_jobs_by_status()` reads from repository |

## Recommendations for production

1. **Set `DATAFORGE_STORAGE_BACKEND=postgres`.** SQLite is not safe
   for multi-process deployments.

2. **Ensure `DATAFORGE_WORKER_QUEUE=true`** so the worker reads go
   through the repository rather than relying on the in-memory dict.

3. **Accept the eventual-consistency window.** The in-memory dict
   is a few seconds behind the DB at worst. For web-scraping
   workloads this is acceptable; for financial transactions it is not.

4. **Monitor the divergence.** Log a warning whenever a mutation
   succeeds in-memory but fails in the DB. The `clear_terminal_jobs`
   and `clear_recycle_bin` handlers already track `failed_ids`.

5. **Consider read-through caching** for a future refactor (Phase 3).
   The `get_job()` method on `SQLiteJobRepository` already does a
   targeted PK lookup and could serve as the cache-fill function.
