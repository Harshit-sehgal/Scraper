# Benchmark Plan

DataForge needs repeatable, lawful, local-first benchmarks before any
production readiness claim. Live-site benchmarks are useful for trend
watching, but they are not deterministic proof.

## Benchmark Tiers

| Tier | Source | Network | Purpose | CI Use |
| --- | --- | --- | --- | --- |
| Smoke | local fixtures and config imports | none | Fast regression signal | required quick/full gate |
| Corpus | local HTML/JSON fixtures with expected outputs | none | Accuracy and failure classification | required before launch gate |
| Golden live | selected accessible public demo sites | yes | Observational external drift | scheduled/manual only |
| Performance | local fixtures plus browser lifecycle | none | Runtime and timeout trend | nightly/full |

## Required Corpus

The benchmark corpus should include:

- static product pages
- listing pages
- tables
- articles
- search result pages
- pagination
- infinite scroll
- load-more
- session/workflow mock pages
- network JSON-backed pages
- empty/no-result pages
- malformed HTML
- login-required mock pages
- blocked/challenge mock pages

## Current Local Corpus Coverage

Updated 2026-06-24 from `backend/tests/test_benchmark_fixtures.py`.
Every required category below has at least one named local fixture and
is enforced by `test_required_benchmark_corpus_categories_have_local_fixtures`.

| Category | Fixture(s) |
| --- | --- |
| static product pages | `travel_site.html` |
| listing pages | `legacy_directory.html` |
| tables | `table_catalog.html` |
| articles | `messy_blog.html` |
| search result pages | `search_results.html` |
| pagination | `search_results.html` |
| infinite scroll | `infinite_scroll_mock.html` |
| load-more | `load_more_mock.html` |
| session/workflow mock pages | `session_expired.html`, `workflow_search_mock.html` |
| network JSON-backed pages | `network_catalog_page.html`, `network_catalog_payload.json` |
| empty/no-result pages | `empty_results.html` |
| malformed HTML | `malformed_listing.html` |
| login-required mock pages | `login_wall_mock.html` |
| blocked/challenge mock pages | `challenge_mock.html` |

## Required Metrics

Each benchmark report should include:

- field precision
- field recall
- row precision
- row recall
- F1
- records found
- missing required fields
- invalid types
- duplicates
- timeout rate
- runtime
- browser failures

## Current Local Corpus Gate

Updated 2026-06-24 from
`backend/benchmarks/local_corpus_expected.json` and
`backend/benchmarks/local_corpus.py`.

The local corpus now has versioned expected outputs and per-case
thresholds for every required category. The scorer is deterministic and
uses only checked-in HTML/JSON fixtures: no live sites, no browser, and
no LLM calls.

Current artifact paths:

- `artifacts/benchmarks/latest_local_corpus.json`
- `artifacts/benchmarks/latest_local_corpus.md`

Current local corpus result:

| Metric | Value |
| --- | ---: |
| version | `2026-06-24.local-corpus.v1` |
| cases | 14 |
| row F1 | 1.0 |
| field F1 | 1.0 |
| false-positive records on negative pages | 0 |
| browser failures | 0 |

## Current Commands

Local-only smoke:

```bash
python3 scripts/run_benchmark_smoke.py
```

Local-only corpus scorer:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m benchmarks.local_corpus
```

Existing in-corpus benchmark command:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest backend/tests/test_benchmark_fixtures.py backend/benchmarks/test_local_corpus_baseline.py backend/benchmarks/test_benchmark_smoke.py \
  -q -m "not live_benchmark and not browser and not golden_dataset" -o addopts=
```

Manual live golden dataset:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest -v backend/tests/test_golden_dataset.py --run-golden-dataset -o addopts=
```

## Launch Gate Recommendation

Do not use benchmark results as launch proof until:

- all required local corpus categories exist and remain enforced: current
  local gate satisfies this for checked-in fixtures
- expected outputs are versioned: current local gate satisfies this via
  `backend/benchmarks/local_corpus_expected.json`
- thresholds are documented per category: current local gate satisfies
  this for local fixture extraction
- failures produce actionable classification: current local negative
  fixtures enforce empty/login/challenge/session-expired classifications
- benchmark reports are archived as artifacts: current local gate writes
  `artifacts/benchmarks/latest_local_corpus.*`
- CI enforces smoke/corpus gates without live-site dependency: local
  pytest coverage exists under `backend/benchmarks`; keep production
  readiness claims blocked on staging, browser, golden-live, load, and
  operational evidence
