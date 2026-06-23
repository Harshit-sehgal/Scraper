# Golden Dataset — Real-World Extraction Validation

**Status:** ✅ **Partially implemented** — sites.json and expected outputs exist
for 5 real-world demo websites. Tests are **observational** (log F1 but do not
fail on mismatch) and skipped by default (`--run-golden-dataset`).

## Purpose

A "golden dataset" is a collection of real-world URLs with known expected outputs.
Running extraction against these URLs and comparing results against the golden
(expected) output is the most honest way to measure real extraction accuracy.

## Current State

- ✅ **Fixture-based benchmarks** exist at `backend/benchmarks/` — these use simplified
  HTML fixtures, not real websites.
- ✅ **`sites.json`** exists with 5 target sites (books.toscrape.com, quotes.toscrape.com,
  scrapethissite.com, example.com, httpbin.org).
- ✅ **Expected output files** exist for all 5 sites in `backend/tests/golden_dataset/expected/`.
- ⚠️ **Tests are observational** — they log F1 scores but do not assert minimum accuracy
  thresholds. Thresholds must be refined through real-world validation.
- ⚠️ **Live benchmark validation** is manual, not automated. Run via the golden-dataset
  `--run-golden-dataset` flag.

## Structure

```
backend/tests/golden_dataset/
├── README.md              (this file)
├── sites.json             (metadata about 5 test sites)
├── expected/
│   ├── books_toscrape.json
│   ├── quotes_toscrape.json
│   ├── scrapethissite_simple.json
│   ├── example_com.json
│   └── httpbin_html.json
└── test_golden_dataset.py (pytest runner — skipped by default)
```

### `sites.json` Structure

```json
{
  "sites": [
    {
      "id": "books_toscrape",
      "url": "https://books.toscrape.com/",
      "description": "Books to Scrape — demo ecommerce site",
      "schema": {
        "fields": {
          "title": {"type": "string", "required": true},
          "price": {"type": "currency"},
          "rating": {"type": "string"}
        }
      },
      "category": "ecommerce",
      "min_expected_records": 20
    }
  ]
}
```

## Running the Tests

```bash
# Default: skipped cleanly
PYTHONPATH=backend python3 -m pytest backend/tests/test_golden_dataset.py

# With network access to real sites
PYTHONPATH=backend python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -v
```

## Limitations

- Tests require network access to real, externally hosted websites.
- Tests may fail flakily if target sites change structure.
- F1 scoring is logged but not asserted — thresholds need refinement.
- Not a substitute for real accuracy benchmarks.

## Related Resources

- `backend/benchmarks/` — Fixture-based benchmark framework
- `backend/tests/test_golden_dataset.py --run-golden-dataset` — Golden-dataset runner
  (network required, observational)
