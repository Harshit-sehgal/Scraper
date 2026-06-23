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

## Current Commands

Local-only smoke:

```bash
python3 scripts/run_benchmark_smoke.py
```

Existing in-corpus benchmark command:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest backend/tests/test_benchmark_fixtures.py backend/benchmarks/test_benchmark_smoke.py \
  -q -m "not live_benchmark and not browser and not golden_dataset" -o addopts=
```

Manual live golden dataset:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest -v backend/tests/test_golden_dataset.py --run-golden-dataset -o addopts=
```

## Launch Gate Recommendation

Do not use benchmark results as launch proof until:

- all required local corpus categories exist and remain enforced
- expected outputs are versioned
- thresholds are documented per category
- failures produce actionable classification
- benchmark reports are archived as artifacts
- CI enforces smoke/corpus gates without live-site dependency
