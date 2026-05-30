# Golden Dataset — Real-World Extraction Validation

**Status:** 🚧 **PLACEHOLDER** — Real-world extraction validation is not yet implemented.

## Purpose

A "golden dataset" is a collection of real-world URLs with known expected outputs.
Running extraction against these URLs and comparing results against the golden
(expected) output is the most honest way to measure real extraction accuracy.

## Current State

- ✅ **Fixture-based benchmarks** exist at `backend/benchmarks/` — these use simplified
  HTML fixtures, not real websites. Accuracy: 85%+ F1 on test data.
- ❌ **Golden dataset with real-world websites** not yet created.
- ❌ **Live benchmark scripts** exist at `scripts/live_benchmark.py` and
  `scripts/validate_books.py` but are manual, not automated.

## Planned Structure

When implemented, the golden dataset should follow this structure:

```
backend/tests/golden_dataset/
├── README.md              (this file)
├── sites.json             (metadata about test sites)
├── expected/
│   ├── example_com.json   (expected output for https://example.com)
│   ├── books_site.json    (expected output for books.toscrape.com)
│   └── ...
└── test_golden_dataset.py (pytest runner that validates extraction)
```

### `sites.json` Schema

```json
{
  "sites": [
    {
      "id": "example_com",
      "url": "https://example.com",
      "description": "Example domain for basic connectivity",
      "schema": {
        "fields": {
          "title": {"type": "string", "required": true},
          "description": {"type": "string"}
        }
      },
      "category": "static",
      "expected_record_count": 1
    }
  ]
}
```

### Expected Output Format

Each expected output file should contain the exact records expected from extraction:

```json
[
  {
    "title": "Example Domain",
    "description": "This domain is for use in illustrative examples..."
  }
]
```

## Implementation Notes

- Golden dataset validation should use `scripts/validate_books.py` and
  `scripts/validate_flights.py` as reference implementations.
- Tests should be marked with `@pytest.mark.golden_dataset` and skipped by default
  (require explicit `--run-golden-dataset` flag to avoid flaky CI failures from
  real website changes).
- Accuracy should be measured as F1 score at the record level.
- Record extra/missing fields should be penalized (as implemented in benchmark
  accuracy scoring).

## Related Resources

- `backend/benchmarks/` — Fixture-based benchmark framework
- `scripts/live_benchmark.py` — Manual live benchmark runner
- `scripts/validate_books.py` — Validation against books.toscrape.com
- `scripts/validate_flights.py` — Validation against flightsnholidays.co.uk
- `docs/audit/DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md` — Benchmark audit
