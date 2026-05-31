# Benchmarks

**Last refreshed:** 2026-06-01
**Status:** Benchmark tooling exists; real-world extraction accuracy is not proven

## Current Verified Benchmark Command

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=
```

Result:

```text
1 passed in 0.27s
```

This is an offline smoke/config test. It does not run live extraction and does not prove accuracy.

## Golden Dataset Status

Files exist:

- `backend/tests/golden_dataset/sites.json`
- `backend/tests/golden_dataset/expected/books_toscrape.json`
- `backend/tests/golden_dataset/expected/example_com.json`
- `backend/tests/golden_dataset/expected/httpbin_html.json`
- `backend/tests/golden_dataset/expected/quotes_toscrape.json`
- `backend/tests/golden_dataset/expected/scrapethissite_simple.json`

The golden test computes record-level F1 when expected output exists, but it currently logs the score and does not enforce a minimum threshold. A live run in this audit was stopped after one visible test and several minutes without progress. Therefore golden accuracy is unvalidated.

## Benchmark Classification

| Category | Status | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| `backend/benchmarks/test_benchmark_smoke.py` | Smoke test | Benchmark package imports/configures | Extraction accuracy |
| Standalone `benchmark_*.py` scripts | Manual/simulated | Useful exploratory checks | Default test health |
| Fixture extraction tests | Synthetic | Regression behavior on controlled HTML | Live website behavior |
| Hostile/recovery simulations | Simulated | Code behavior under generated conditions | Anti-bot resilience |
| Replay/longevity modules | Simulated/manual | Internal state behavior | Production reliability |
| Golden dataset tests | Optional/incomplete | Can support future accuracy validation | Current benchmark proof |

## Allowed Claims

- The project includes benchmark and golden-dataset scaffolding.
- The benchmark pytest smoke test passes.
- Golden expected-output files exist.

## Banned Claims

Do not claim 100% accuracy, fully benchmarked, proven real-world accuracy, anti-bot tested, or works on every website.

## Required Real Benchmark Report

A credible benchmark report needs dataset permission notes, site/page counts, static versus JavaScript classification, schemas, expected outputs, actual outputs, precision, recall, F1, failure cases, thresholds, and reproduction commands.
