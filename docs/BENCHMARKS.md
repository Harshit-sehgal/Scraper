# Benchmarks

**Last refreshed:** 2026-06-02
**Status:** Benchmark tooling exists; real-world extraction accuracy is not proven

## Current Verified Benchmark Command

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=
```

Result:

```text
1 passed, 1 skipped in 0.26s
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

The golden test computes record-level F1 when expected output exists and now enforces modest per-site thresholds from `sites.json`. The current live command completed with `8 passed in 53.97s`: books `F1=0.650`, quotes `F1=1.000`, countries `F1=0.680`, example `F1=1.000`, and httpbin `F1=1.000`. This is useful regression evidence, not proof of broad real-world extraction accuracy.

## Benchmark Classification

| Category | Status | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| `backend/benchmarks/test_benchmark_smoke.py` | Smoke test | Benchmark package imports/configures | Extraction accuracy |
| Standalone `benchmark_*.py` scripts | Manual/simulated | Useful exploratory checks | Default test health |
| Fixture extraction tests | Synthetic | Regression behavior on controlled HTML | Live website behavior |
| Hostile/recovery simulations | Simulated | Code behavior under generated conditions | Anti-bot resilience |
| Replay/longevity modules | Simulated/manual | Internal state behavior | Production reliability |
| Golden dataset tests | Optional/live | Enforced modest F1 thresholds on five accessible sample sites | Broad benchmark proof |

## Allowed Claims

- The project includes benchmark and golden-dataset scaffolding.
- The benchmark pytest smoke test passes.
- Golden expected-output files exist and the current live suite passes modest enforced thresholds.

## Banned Claims

Do not claim 100% accuracy, fully benchmarked, proven real-world accuracy, anti-bot tested, or works on every website.

## Required Real Benchmark Report

A credible benchmark report needs dataset permission notes, site/page counts, static versus JavaScript classification, schemas, expected outputs, actual outputs, precision, recall, F1, failure cases, thresholds, and reproduction commands.
