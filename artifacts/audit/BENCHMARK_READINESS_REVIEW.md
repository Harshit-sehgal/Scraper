# Benchmark Readiness Review

Date: 2026-06-12
Commit: `7d47045`
Scope: Prompt 7 P1 baseline. No product feature work.

## Evidence Inspected

- `docs/BENCHMARKS.md`
- `scripts/run_benchmarks.sh`
- `scripts/live_benchmark.py`
- `backend/benchmarks/test_benchmark_smoke.py`
- `backend/tests/test_benchmark_fixtures.py`
- `backend/tests/test_golden_dataset.py`
- `backend/tests/golden_dataset/sites.json`
- `backend/app/benchmark_accuracy.py`
- `backend/app/benchmark_reporter.py`
- `.github/workflows/ci.yml`
- `.github/workflows/golden-dataset.yml`

## Current State

Benchmark scaffolding exists. The repository has fixture-based tests,
benchmark package smoke tests, golden-dataset definitions, accuracy
metrics, and CI jobs for in-corpus benchmarks and weekly/manual live
golden-dataset tests.

Current local smoke evidence:

- Command: `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests/test_benchmark_fixtures.py backend/benchmarks/test_benchmark_smoke.py -q -m "not live_benchmark and not browser and not golden_dataset"`
- Exit: 0
- Result: 8 passed

Prompt 7 added `scripts/run_benchmark_smoke.py`, which writes:

- `artifacts/benchmarks/latest_smoke.json`
- `artifacts/benchmarks/latest_smoke.md`

## Coverage Against Required Corpus

| Corpus Area | Status | Evidence | Next Action |
| --- | --- | --- | --- |
| Static product pages | partial | fixture pages and golden sites exist | Add named local fixture with expected output |
| Listing pages | partial | `messy_blog`, golden demo sites | Broaden local listing fixtures |
| Tables | partial | live benchmark definitions include tables | Add local table fixture/golden output |
| Articles | partial | article-like fixtures exist but not full corpus | Add expected outputs and metrics |
| Search result pages | partial | golden/live definitions include search-like pages | Add local search-results fixture |
| Pagination | partial | golden quotes/books pages imply pagination | Add local paginated fixture with row recall |
| Infinite scroll | missing | no verified local fixture in Prompt 7 | Add bounded local JS fixture |
| Load-more | missing | no verified local fixture in Prompt 7 | Add bounded local JS fixture |
| Session/workflow mock pages | missing | workflow tests exist, benchmark corpus does not cover this | Add local workflow mock corpus |
| Network JSON-backed pages | partial | network extractor tests exist | Add benchmark fixture with captured local JSON |
| Empty/no-result pages | partial | `test_benchmark_fixtures.py` checks empty/shell pages | Add golden expected failure classifications |
| Malformed HTML | partial | fixture corpus has varied HTML | Add explicit malformed fixture |
| Login-required mock pages | missing | no local benchmark fixture verified | Add login-wall fixture; no bypass behavior |
| Blocked/challenge mock pages | partial | `8f2aabc1ca59` anti-bot/challenge fixture | Add expected classification thresholds |

## Metrics Readiness

Existing code supports precision, recall, F1, completeness,
schema conformity, duplicate rate, and field accuracy in
`backend/app/benchmark_accuracy.py`. The benchmark reporter persists
precision/recall/fallback/latency history.

Required future metrics still need a consolidated benchmark report:
field precision, field recall, row precision, row recall, F1, records
found, missing required fields, invalid types, duplicates, timeout
rate, runtime, and browser failures.

## Live Site Dependency

The default smoke runner added in Prompt 7 does not use live sites.
Existing golden dataset and live benchmark workflows can use live sites
only under explicit flags or scheduled/manual CI. They should remain
non-blocking for ordinary local validation unless explicitly requested.

## Readiness Status

Status: partial. Safe local smoke foundation exists. Full benchmark
readiness still needs broader local fixtures, expected outputs, quality
thresholds, and CI enforcement policy.
