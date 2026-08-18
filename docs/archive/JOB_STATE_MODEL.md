# Job State Model

Current truth source: `docs/AGENT_TRUTH.md`.

This document describes the current job lifecycle observed in code. It is not a production readiness claim.

## State Enum

`backend/app/models.py` defines `JobStatus` values used by route handlers, storage, and runner services:

- `pending`
- `discovering`
- `running`
- `completed`
- `degraded`
- `empty_result`
- `failed`
- `canceled`

## Current Transition Sources

| Transition area | Code evidence | Notes |
| --- | --- | --- |
| Create | `backend/app/routers/jobs_write.py` creates `Job(...)`, stores it, persists it, and schedules execution. | Created jobs start from the model default status, then are scheduled. |
| Discovery | `backend/app/services/discovery.py` sets `JobStatus.DISCOVERING` for auto mode and can set `FAILED` on discovery failure. | Discovery is skipped for manual mode. |
| Running | `backend/app/services/job_runner.py` sets `JobStatus.RUNNING` before scraping. | Manual mode initializes progress totals from URL count. |
| Cancellation | `backend/app/services/job_runner.py`, `backend/app/routers/jobs_write.py`, and `app.utils.job.mark_job_canceled` coordinate cancellation. | Cross-process cancellation checks repository `is_cancel_requested`. |
| Final terminal classification | `backend/app/services/finalization.py` calls `classify_job_status` in `backend/app/services/status_classifier.py`. | Terminal success states are `completed`, `degraded`, and `empty_result`. |
| Failure | `backend/app/services/job_runner.py` catches exceptions, sets `FAILED`, records error, and persists critical state. | Error string is user-visible through job APIs. |
| Startup recovery | `backend/app/state_store.py` and `backend/app/postgres_repository_base.py` recover in-progress jobs as failed when configured. | This prevents indefinitely running jobs after restart. |

## Intended Lifecycle

```text
pending
  -> discovering      auto mode only
  -> running
  -> completed        all URLs produced records
  -> degraded         some URLs produced records
  -> empty_result     no records or no URLs
  -> failed           exception, discovery failure, recovery after restart
  -> canceled         cancellation before or during execution
```

`completed`, `degraded`, `empty_result`, `failed`, and `canceled` are terminal for normal route behavior.

## Current Risks

- State transitions are spread across routers, runner services, finalization, startup recovery, and utility helpers.
- There is no single domain-level state machine enforcing allowed transitions.
- Startup recovery and cancellation behavior differ by storage/process mode.
- Reclean/backfill routes can temporarily move terminal jobs back to running behavior and need explicit tests before refactor.

## Future Boundary

Before adding Workflow Replay, scheduled monitoring expansion, or SaaS billing enforcement, create a small domain module such as `app.domain.job_state` that owns:

- allowed transitions
- terminal-state predicate
- transition audit metadata
- cancellation and restart-recovery semantics

Do not change current behavior without characterization tests for create, cancel, reclean, failure, empty result, degraded result, and restart recovery.
