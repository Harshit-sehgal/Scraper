# Benchmarks

**Last refreshed:** 2026-06-24
**Status:** Deterministic local corpus gate exists; real-world extraction accuracy is not proven

## Current Verified Benchmark Command

```bash
python3 scripts/run_benchmark_smoke.py
```

Result:

```text
33 passed, 2 skipped, 1 deselected
```

This is a local-only smoke plus corpus gate. It does not run live
extraction and does not prove real-world accuracy.

## Local Corpus Status

The deterministic corpus uses checked-in fixtures and versioned expected
outputs:

- manifest: `backend/benchmarks/local_corpus_expected.json`
- scorer: `backend/benchmarks/local_corpus.py`
- tests: `backend/benchmarks/test_local_corpus_baseline.py`
- latest JSON: `artifacts/benchmarks/latest_local_corpus.json`
- latest Markdown: `artifacts/benchmarks/latest_local_corpus.md`

Latest local corpus result:

| Metric | Value |
| --- | ---: |
| cases | 14 |
| row F1 | 1.0 |
| field F1 | 1.0 |
| false-positive records on negative pages | 0 |
| browser failures | 0 |
| live sites used | false |

## Golden Dataset Status

Files exist:

- `backend/tests/golden_dataset/sites.json`
- `backend/tests/golden_dataset/expected/books_toscrape.json`
- `backend/tests/golden_dataset/expected/example_com.json`
- `backend/tests/golden_dataset/expected/httpbin_html.json`
- `backend/tests/golden_dataset/expected/quotes_toscrape.json`
- `backend/tests/golden_dataset/expected/scrapethissite_simple.json`

The golden test computes record-level F1 when expected output exists and now enforces modest per-site thresholds from `sites.json`. Previous live results: books `F1=0.650`, quotes `F1=1.000`, countries `F1=0.680`, example `F1=1.000`. Scores may vary with site changes; rerun `pytest backend/tests/golden_dataset/ -v` for fresh numbers.

## Benchmark Classification

| Category | Status | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| `backend/benchmarks/test_benchmark_smoke.py` | Smoke test | Benchmark package imports/configures | Extraction accuracy |
| `backend/benchmarks/test_local_corpus_baseline.py` | Local deterministic corpus | Expected-output and threshold behavior on checked-in fixtures | Live website behavior or production accuracy |
| Standalone `benchmark_*.py` scripts | Manual/simulated | Useful exploratory checks | Default test health |
| Fixture extraction tests | Synthetic | Regression behavior on controlled HTML | Live website behavior |
| Hostile/recovery simulations | Simulated | Code behavior under generated conditions | Anti-bot resilience |
| Replay/longevity modules | Simulated/manual | Internal state behavior | Production reliability |
| Golden dataset tests | Optional/live | Enforced modest F1 thresholds on five accessible sample sites | Broad benchmark proof |

## Allowed Claims

- The project includes benchmark and golden-dataset scaffolding.
- The benchmark pytest smoke test passes.
- The local deterministic corpus has versioned expected outputs and
  threshold checks for checked-in fixtures.
- Golden expected-output files exist; treat live results as fresh only
  after rerunning the golden dataset command against current sites.

## Banned Claims

Do not claim 100% accuracy, fully benchmarked, proven real-world accuracy, anti-bot tested, or works on every website.

## Required Real Benchmark Report

A credible benchmark report needs dataset permission notes, site/page counts, static versus JavaScript classification, schemas, expected outputs, actual outputs, precision, recall, F1, failure cases, thresholds, and reproduction commands.
