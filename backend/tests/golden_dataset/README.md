# Golden Dataset — Real-World Extraction Validation (E3.1–E3.3)

**Status:** ✅ **Implemented** — 10 live sites, versioned expected outputs,
per-site F1 ≥ 0.9 gate, diagnosis cards on failure, weekly CI with a
>5pt regression alert.

## Purpose

A "golden dataset" is a collection of real-world URLs with known expected
outputs. Running extraction against these URLs and comparing results
against the golden (expected) output is the most honest way to measure
real extraction accuracy.

## Current State

- ✅ **10 sites** with expected outputs in `expected/` — toscrape
  catalogs (4), quotes tag pages (3), example.com, httpbin, and
  ScrapeThisSite.
- ✅ **Versioned dataset**: `sites.json` carries `version` (bumped when
  expected outputs change).
- ✅ **Hard F1 gate per site** (`min_f1`, E3.2 ≥ 0.9): below-threshold
  sites fail the run AND write a diagnosis card to
  `artifacts/golden_dataset/diagnosis/<site>.json` with the failure
  taxonomy from `app.failure_classification` plus field-level F1.
- ✅ **Trend tracking** (`trend.jsonl`, committed): each run appends
  per-site F1; a drop of more than 5 points vs the previous run fails
  with an explicit ACCURACY REGRESSION alert.
- ✅ **Weekly CI** (`.github/workflows/golden-dataset.yml`, Sunday 03:00
  UTC): runs with 3 retries (sites flake on first fetch), publishes the
  trend + diagnosis cards as workflow artifacts, and notifies Telegram.

## Structure

```
backend/tests/golden_dataset/
├── README.md              (this file)
├── sites.json             (versioned site definitions, min_f1 gates)
├── trend.jsonl            (per-site F1 history, committed)
├── expected/
│   ├── books_toscrape.json
│   ├── books_toscrape_page2.json
│   ├── books_travel.json
│   ├── books_mystery.json
│   ├── quotes_toscrape.json
│   ├── quotes_love.json
│   ├── quotes_inspirational.json
│   ├── scrapethissite_simple.json
│   ├── example_com.json
│   └── httpbin_html.json
└── test_golden_dataset.py (pytest runner — skipped by default)
```

## Running the Tests

```bash
# Default: skipped cleanly
PYTHONPATH=backend python3 -m pytest backend/tests/test_golden_dataset.py

# With network access to real sites (CI-style retries)
PYTHONPATH=backend python3 -m pytest backend/tests/test_golden_dataset.py \
  --run-golden-dataset --reruns 3 --reruns-delay 10 -o addopts=
```

## Adding a Site

1. Verify the site is a lawful, consenting public catalog (see AUP).
2. Run extraction in isolation and write the full result (minus
   `record_score`) to `expected/<id>.json` — see the test for the
   schema format.
3. Add the site to `sites.json` with `min_expected_records`, `min_f1`
   (≥ 0.9 for the E3.2 gate), and `timeout_seconds`.
4. Run the suite; confirm two consecutive passes; commit the trend
   baseline.

## Limitations

- Tests require network access to real, externally hosted websites and
  may flake on first fetch (toscrape rate-limits bursts) — retries are
  built into the CI workflow.
- Sites that start blocking bots (e.g., ScrapeThisSite 403 in 2026-08)
  are kept so the diagnosis cards + trend alert surface the regression
  instead of hiding it.

## Related Resources

- `backend/benchmarks/local_corpus.py` — deterministic offline corpus
- `backend/app/golden_corpus.py` — field-level F1, diagnosis cards, trend
- `backend/tests/test_golden_corpus.py` — unit tests (run in default CI)
