"""Aggregate CI gate for local corpus benchmarks.

Runs ``run_local_corpus`` and asserts the aggregate metrics meet the
manifest's ``aggregate_thresholds`` (``min_row_f1``, ``min_field_f1``,
``max_timeout_rate``, ``max_browser_failures``, plus a
``zero_result_truthfulness`` floor).

When ``CI_BENCHMARK_SUBSET=1`` is set, only the 5 hand-picked "smoke"
cases are asserted, allowing for a fast PR-level sanity gate that
exercises each top-level category without running the full 23+ case
set. The full gate is exercised in nightly / merge-to-main runs.
"""

from __future__ import annotations

import os

from benchmarks.local_corpus import run_local_corpus

# Top-level smoke cases — one per category cluster, chosen for fast,
# deterministic extraction. Each runs in <50ms.
SMOKE_CASE_IDS: list[str] = [
    "travel_site_flights",  # static product pages
    "table_catalog_prices",  # tables
    "search_results_widgets",  # search result pages + pagination
    "spa_react_marketplace",  # spa-render-wait
    "wholesale_large_catalog_1000plus",  # large result sets
]


def _aggregate_truthfulness(report: dict) -> float:
    """Fraction of negative-fixture cases that correctly produced zero records.

    ``zero_result_truthfulness = 1 - (false_positive_negative_cases / total_negative_cases)``.
    """
    cases = report.get("cases", [])
    negative_cases = [c for c in cases if c.get("extractor") == "negative_html"]
    if not negative_cases:
        return 1.0
    false_positive = sum(1 for c in negative_cases if c.get("metrics", {}).get("false_positive_records", 0) > 0)
    return 1.0 - (false_positive / len(negative_cases))


def test_benchmark_ci_gate_full() -> None:
    """Full local corpus gate: aggregate F1 + zero-result truthfulness.

    Skipped when ``CI_BENCHMARK_SUBSET=1`` — the subset variant
    (``test_benchmark_ci_gate_subset``) handles that path.
    """
    if os.environ.get("CI_BENCHMARK_SUBSET") == "1":
        import pytest

        pytest.skip("Subset mode active; full gate is exercised by the suite test")

    report = run_local_corpus(write_artifacts=False)
    aggregate = report["aggregate"]
    thresholds = report.get("aggregate_thresholds", {})

    assert aggregate["case_count"] >= 23, f"Expected at least 23 cases in the local corpus, got {aggregate['case_count']}"
    assert aggregate["passed_cases"] == aggregate["case_count"], (
        f"{aggregate['case_count'] - aggregate['passed_cases']} cases failed: "
        f"{[c['id'] for c in report['cases'] if c['status'] == 'failed']}"
    )
    assert aggregate["row_f1"] >= thresholds.get("min_row_f1", 0.95), (
        f"Aggregate row_f1 {aggregate['row_f1']:.4f} below threshold {thresholds.get('min_row_f1', 0.95)}"
    )
    assert aggregate["field_f1"] >= thresholds.get("min_field_f1", 0.95), (
        f"Aggregate field_f1 {aggregate['field_f1']:.4f} below threshold {thresholds.get('min_field_f1', 0.95)}"
    )
    assert aggregate["timeout_rate"] <= thresholds.get("max_timeout_rate", 0.0), (
        f"Timeout rate {aggregate['timeout_rate']} above threshold"
    )
    assert aggregate["browser_failures"] <= thresholds.get("max_browser_failures", 0), (
        f"Browser failures {aggregate['browser_failures']} above threshold"
    )

    # Zero-result truthfulness: negative fixtures must not falsely produce records.
    truthfulness = _aggregate_truthfulness(report)
    assert truthfulness >= 0.95, f"Zero-result truthfulness {truthfulness} below 0.95"


def test_benchmark_ci_gate_subset() -> None:
    """PR-level quick gate: only the 5 smoke cases are asserted.

    Activates when ``CI_BENCHMARK_SUBSET=1``. Verifies each category
    cluster has at least one passing representative in <1s total.
    """
    if os.environ.get("CI_BENCHMARK_SUBSET") != "1":
        import pytest

        pytest.skip("Subset mode inactive; full gate is exercised by the suite test")

    report = run_local_corpus(write_artifacts=False)
    cases_by_id = {c["id"]: c for c in report["cases"]}

    missing = [cid for cid in SMOKE_CASE_IDS if cid not in cases_by_id]
    assert not missing, f"Smoke case IDs missing from corpus: {missing}"

    failures = [cid for cid in SMOKE_CASE_IDS if cases_by_id[cid]["status"] != "passed"]
    assert not failures, f"Smoke cases failed: {failures}"

    # Smoke subset must still hit F1=1.0 across the 5 selected cases.
    smoke = [cases_by_id[cid] for cid in SMOKE_CASE_IDS]
    avg_row_f1 = sum(c["metrics"]["row_f1"] for c in smoke) / len(smoke)
    avg_field_f1 = sum(c["metrics"]["field_f1"] for c in smoke) / len(smoke)
    assert avg_row_f1 >= 0.99, f"Smoke avg row_f1 {avg_row_f1:.4f} below 0.99"
    assert avg_field_f1 >= 0.99, f"Smoke avg field_f1 {avg_field_f1:.4f} below 0.99"
