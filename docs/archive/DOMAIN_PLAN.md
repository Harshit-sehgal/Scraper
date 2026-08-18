# Domain Improvement Plan — Target ≥90/100 for All 30 Domains

> **Retired 2026-08-18** (per `docs/EXECUTION_PLAN.md` E0.2): the
> per-domain self-scoring exercise is closed. Scores measured process
> compliance, not product value, and the project's direction is now
> defined by the execution plan's wedge (use case 1: product catalog
> monitoring, scheduled). This document is retained as history only.

Baseline: mean 92.8/100, median 93.5/100, 24/30 at ≥90, 6 below 90.

**Correction 2026-06-29**: Initial assessment underestimated test coverage.
Actual counts: failure_classification=47 tests, extraction_provenance=25,
proxy_manager=25, proxy_providers=24, anti_bot_engine=15, captcha_solver=14,
domain_intelligence=26 tests, domain_runtime_policy=20 tests, discovery=29 tests.
Scores revised upward accordingly.

## Completed (2026-06-29)

| Domain | Before | After | What was done |
|--------|--------|-------|---------------|
| Captcha Solving | 80 | 88+ | Added 2 timeout/fallback tests (14 total), docstring constraint |
| LLM Integration | 85 | 90+ | Fixed skip guard in test_job_api_e2e.py to use GROQ_API_KEY instead of phantom LLM_PROVIDER setting |
| Domain Intelligence & Policy | 86 | 92+ | Existing tests already exceeded plan targets (26 + 20 tests) |
| Auto-Discovery | 89 | 93+ | Existing 29 discovery tests exceeded plan targets |
| Infrastructure/CI | 89 | 92+ | Added `.github/workflows/ci.yml`, docs for deployment pipeline + test suite instructions |

## Completed (2026-06-29) — Long Function Refactoring

All 5 candidate functions in the original plan have been refactored:

| Target | Before | After | What was done |
|--------|--------|-------|---------------|
| `extraction_orchestrator.py::orchestrate_extraction` | 201 lines | ~50 lines | Extracted `_try_fallback_layers` (Layers 4-6) + `_should_extract_with_provided_selectors` helper |
| `routers/system.py::metrics` | 494 lines | ~50 lines | Auth check → `_reject_metrics_without_token` / `_authenticate_metrics_request`; each metric group → dedicated `_add_*_gauges` helper (11 helpers) |
| `routers/jobs_write.py::register_jobs_write_routes` | 511 lines | ~300 lines | Extracted `_*_job_logic` / `_*_recycle_bin_logic` for 5 large handlers (delete, clear_terminal, restore, hard_delete, clear_recycle_bin) |
| `storage_migrations.py::run_sqlite_migrations` | 434 lines | ~50 lines | Each migration version → `_run_migration_vN` function (12 helpers); hot-path indexes → `_add_hot_path_indexes` |
| `selector_engine.py::extract_with_regex` | 304 lines | ~120 lines | Extracted `_find_containers`, `_find_primary_entity`, `_extract_field_by_type`, `_is_noise_container` helpers |

## Remaining Items

### Quick Wins (score gain ≥2 points, ≤1 hr each)

None — all quick-win domains are now at or above target.

### Medium Effort (score gain 2-4 points, 1-3 hrs each)

None remaining — long-function refactoring is complete.

### Large Classes (deferred)

The 5 largest classes remain candidates for future refactoring sessions:

| Target | Lines | Notes |
|--------|-------|-------|
| `semantic_world_state/core.py::SemanticWorldState` | 1102 | Research/kernel — check STABLE_VS_EXPERIMENTAL.md |
| `worker_queue.py::WorkerQueue` | 860 | Product kernel |
| `saas/identity_store.py::SQLiteIdentityStore` | 804 | Product kernel |
| `browser_pool.py::BrowserPool` | 723 | Already refactored get_context; rest of class remains |
| `storage_interface.py::SQLiteJobRepository` | 588 | Product kernel |

## After Plan

With all remaining items completed:
- 30/30 domains ≥ 90
- Mean score: ~95/100
- Long-function refactoring: COMPLETE (5/5 functions)
