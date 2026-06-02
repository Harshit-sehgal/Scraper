# Deliverable 5: Test Truth Report

<div style="border: 2px solid #d24646; background: #fef6f6; padding: 1rem 1.2rem; border-radius: 12px; margin-bottom: 1.5rem;">
  <strong style="color: #972a2a; font-size: 0.95rem;">⚠ HISTORICAL DOCUMENT</strong><br>
  <span style="color: #607069; font-size: 0.85rem;">
    This archived deliverable was generated during a prior cleanup cycle. It is preserved for reference only.
    Do not treat it as current evidence. Always consult <code>PROJECT_STATUS.md</code> for the current truth source.
  </span>
</div>


**Date:** May 30, 2026
**Method:** `pytest --collect-only`, full test run, manual file inspection.

---

## Test Collection

| Metric | Value |
|--------|-------|
| Test files | 145 |
| Tests collected | 2,207 |
| Test files NOT collected | 15 manual + 4 benchmark + 2 other scripts = 21 |
| Postgres-marked tests | Skipped by default (need `--run-postgres`) |
| Golden-dataset-marked tests | Skipped by default (need `--run-golden-dataset`) |

---

## Test Results (with ENV fix: STORAGE_BACKEND=sqlite)

**Note:** This report uses the corrected environment. Without the fix, ~40+ tests fail due to Postgres env leak.

### Estimated Breakdown

| Outcome | Count (est.) | Notes |
|---------|--------------|-------|
| Passed | ~2,100 | Most tests pass with SQLite backend |
| Failed | ~40 | Root cause: Postgres env leak (E01) |
| Skipped | ~60 | Postgres + golden dataset markers |
| Errors | ~0 | No import errors observed |

### Actual Failures (from test run with broken env)

The following tests failed when `DATAFORGE_STORAGE_BACKEND=postgres` was set without Postgres running:

- **test_api_regressions.py**: 15 failures — Postgres connectivity errors from `/api/system/status` and job operations
- **test_storage_endpoints.py**: 10 failures — `ReadyEndpoint` and `StorageStatusEndpoint` fail when Postgres URL is set but DB unreachable
- **test_job_lifecycle.py**: 8 failures — Job lifecycle tests fail due to storage backend errors
- **test_postgres_repository.py**: 3 failures — Factory tests try Postgres URL resolution
- **test_rbac.py**: 2 failures — Postgres connectivity error in RBAC endpoint guards
- **test_production_hardening.py**: 2 failures — Job cleanup/monitoring tests fail
- **test_ga_hardening.py**: 2 failures — Disk offload and browser pool tests fail
- **test_golden_dataset.py**: 1 failure — Site extraction test fails
- **test_metrics.py**: 1 failure — Health check latency metric test fails
- **test_paginated_results.py**: 1 failure — Backfill metadata endpoint fails
- **test_pyflakes_fixes.py**: 1 failure — Pyflakes assertion failure

---

## Weak Test Areas

| Issue | Severity | Details |
|-------|----------|---------|
| Postgres tests skipped by default | 🟠 High | `--run-postgres` required. Not run in standard `pytest` invocation. |
| Golden dataset tests skipped by default | 🟠 High | `--run-golden-dataset` required. Real extraction accuracy unknown. |
| 15 manual test files not run | 🟠 High | Ad-hoc scripts, no CI integration, no assertion framework. |
| 4 benchmark files not run by pytest | 🟠 High | Not named `test_*.py`. Not collected. |
| Benchmark data is simulated | 🟡 Medium | `benchmarks/hostile.py` uses hardcoded simulation data. |
| Tests with weak assertions | 🟡 Medium | Some tests check "status code is 200" without checking response body. |
| Tests mocking too much | 🟡 Medium | Some tests mock the entire scraper, testing only orchestration. |
| Playwright/browser tests | ❓ Unknown | Need actual browser binaries. Not verified in this session. |

---

## Honest Claim

**The project has a large test suite (2,207 tests) covering many components. Most unit tests pass with SQLite. Postgres, golden dataset, and live browser tests are skipped by default. Around 15 manual tests and 4 benchmarks are not integrated into the pytest framework. Full test confidence requires fixing the Postgres env leak and integrating the benchmark/manual tests.**
