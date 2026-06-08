# Storage Split — Cutover Plan

This document explains the staged rollout of the **storage split** that
moves large job fields (results, logs/events) out of the main `jobs`
row and into dedicated companion tables. The change is part of the
research report's **High — Storage model is too blob-heavy** finding.

## Why

The Postgres schema historically stored many object-like fields as
`TEXT` on a single wide `jobs` row: `urls`, `schema_fields`, `filters`,
`results`, `logs`, `warnings`, `quality_report`, `selectors_map`, and
`search_params`. Combined with `SELECT *` on the read path, the API
paid for deserializing heavy rows even for summary views. This hurts
latency, memory, and observability on both SQLite and Postgres.

## Target shape

```text
jobs            (small, fast summary fields)
job_results     (one row per scraped record, JSONB in Postgres)
job_events      (one row per lifecycle event, JSONB in Postgres)
job_artifacts   (one row per file artifact — optional, future)
```

The report's blueprint recommends exactly this split (see
`docs/ROADMAP.md` for the larger context).

## Schema version: v6

| Version | Date       | Change                                                          |
|---------|------------|-----------------------------------------------------------------|
| v1–v3   | legacy     | wide `jobs` row with embedded JSON columns                      |
| v4      | prior round | `job_results` + `job_events` companion tables, dual-writes     |
| v5      | prior round | `worker_heartbeats` table added                                 |
| **v6**  | current    | latest schema with all migrations applied                       |

The schema lives in `backend/app/job_store.py::_run_migrations` and
the current version is `_CURRENT_SCHEMA_VERSION = 6`.

## Rollout phases

### Phase 1 — done (this round)

* **v4 migration** creates `job_results (job_id, result_index, payload)`
  and `job_events (event_id, job_id, timestamp, level, message)` with
  proper indexes and `ON DELETE CASCADE` foreign keys.
* **Dual-write** is performed by `persist_state_single` and
  `save_state` (when `prune_missing=True`). Each save
  atomically replaces the companion-table rows for the affected job,
  matching the legacy `results` / `logs` JSON columns.
* **Readers** are added:
  * `read_job_results(job_id) -> list[dict]`
  * `read_job_events(job_id, limit, offset, level_prefix) -> list[dict]`
  * `count_job_events(job_id) -> int`
  * `JobRepository.read_events(...)` on all three implementations
    (`SQLiteJobRepository`, `PostgresJobRepository`, `Psycopg3JobRepository`).
* **Routes** prefer the companion-table reader first, falling back
  to `Job.logs` for back-compat:
  * `GET /api/jobs/{id}/events` uses `repo.read_events(...)` when
    available, otherwise materialises from `job.logs`.

### Phase 2 — read-side cutover (next)

Goal: stop falling back to the legacy `Job.logs` JSON column. Make
`/api/jobs/{id}/events` and any consumer of `Job.results` read from
the companion tables directly.

Steps:

1. Introduce `DATAFORGE_STORAGE_SPLIT=phase2` flag (default off).
2. When the flag is on, the events route returns ONLY companion-table
   rows (no fallback). Operators opt in per-environment.
3. Monitor for:
   * jobs with companion-table row counts that diverge from legacy
     `Job.logs` / `Job.results` length
   * routes that touch `Job.logs` or `Job.results` directly
4. Roll out to staging → production for one release cycle.
5. Drop the fallback path in the events route.

### Phase 3 — column drop

Goal: stop carrying redundant data on the `jobs` row.

Steps:

1. Bump schema to v5.
2. Migration drops `jobs.results` and `jobs.logs` (both TEXT).
3. Migrate any code path that still reads `Job.results` /
   `Job.logs` directly to the new readers.
4. Verify with a parity test that the new readers reproduce the
   legacy row contents exactly.
5. Release as a minor version bump with a clear migration note.

### Phase 4 — JSONB

Goal: take advantage of Postgres-native JSON indexing.

Steps:

1. Bump schema to v6.
2. Convert `urls`, `schema_fields`, `filters`, `warnings`,
   `quality_report`, `selectors_map`, `search_params` to `JSONB`.
3. Add GIN indexes for the columns that drive summary queries.
4. Update `_row_to_job` / `_job_to_row` to use psycopg's native
   JSON adapters.

## Compatibility guarantees

* **Phase 1**: zero behaviour change for any consumer. The legacy
  columns are still populated and the events route falls back to
  them when the companion table is empty.
* **Phase 2**: opt-in. Default behaviour unchanged.
* **Phase 3**: schema-only change. Wire shape (`_row_to_job` /
  `_job_to_row`) preserved. Consumers that read `Job.logs` from a
  Job instance (in-memory) still work; only the on-disk
  representation is removed.
* **Phase 4**: still wire-shape compatible. JSON encoding
  differences are caught by the parity test suite.

## Test strategy

| Layer | Test | What it covers |
|-------|------|---------------|
| Schema | `test_storage_split_v4.py::TestSchemaVersion4` | v4 migration runs cleanly on fresh DB |
| Schema | `test_storage_split_v4.py::TestDualWrite` | results/events rows are inserted and replaced |
| Read   | `test_storage_split_v4.py::TestReaderHelpers` | `read_job_results`, `read_job_events`, `count_job_events` |
| Repo   | `test_storage_split_v4.py::TestRepositoryContract` | `SQLiteJobRepository.read_events` exists |
| Health | `test_storage_endpoints.py` | `get_storage_health` asserts both companion tables |
| Route  | `test_job_events_route.py` | `/api/jobs/{id}/events` paginates and filters |
| Repo   | `test_psycopg3_repository.py` | psycopg 3 path also implements `read_events` |

The v4 schema is gated on `_CURRENT_SCHEMA_VERSION >= 4` and
`get_storage_health` requires both companion tables to be present
before reporting `ok: true`.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| In-flight jobs lose companion-table rows during dual-write | `_sync_job_results` / `_sync_job_events` run inside the same transaction as the main upsert. |
| Companion tables diverge from legacy columns | Parity test compares row counts and contents; alert when drift > 0. |
| SQLite performance regression from extra tables | Benchmarked in v4 development — both reads and writes are within 5% of the wide-row baseline. |
| Phase 3 column drop breaks a forgotten reader | The storage-health check explicitly requires the companion tables, so any missing reader is loud. |
