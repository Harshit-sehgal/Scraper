"""Local benchmark corpus baseline tests.

These tests enforce versioned expected outputs and local-only thresholds for
the fixture corpus documented in docs/BENCHMARK_PLAN.md.
"""

from __future__ import annotations

from pathlib import Path

from benchmarks.local_corpus import LOCAL_CORPUS_JSON, LOCAL_CORPUS_MD, REQUIRED_METRICS, load_manifest, run_local_corpus


def test_local_corpus_manifest_covers_required_categories() -> None:
    manifest = load_manifest()
    covered_categories = {category for case in manifest["cases"] for category in case["categories"]}

    assert set(manifest["required_categories"]) <= covered_categories
    assert all(case["expected_records"] or case.get("expected_failure_classes") for case in manifest["cases"])


def test_local_corpus_thresholds_pass_and_report_required_metrics() -> None:
    report = run_local_corpus(write_artifacts=False)

    assert report["status"] == "passed", report["failures"]
    assert report["live_sites_used"] is False
    assert report["browser_required"] is False
    assert report["aggregate"]["row_f1"] >= report["aggregate_thresholds"]["min_row_f1"]
    assert report["aggregate"]["field_f1"] >= report["aggregate_thresholds"]["min_field_f1"]

    for case in report["cases"]:
        assert case["status"] == "passed", case["failures"]
        assert set(case["metrics"]) >= REQUIRED_METRICS


def test_access_block_cases_have_no_false_success_records() -> None:
    report = run_local_corpus(write_artifacts=False)
    negative_cases = {case["id"]: case for case in report["cases"] if case["extractor"] == "negative_html"}

    assert negative_cases["empty_results_page"]["failure_class"] in {"empty_response", "genuinely_empty"}
    assert negative_cases["login_wall_page"]["failure_class"] == "auth_required"
    assert negative_cases["challenge_block_page"]["failure_class"] == "anti_bot_block"
    assert negative_cases["session_expired_page"]["failure_class"] in {"session_bound_url", "search_replay_required"}
    assert all(case["metrics"]["false_positive_records"] == 0 for case in negative_cases.values())


def test_local_corpus_report_writes_json_and_markdown(tmp_path: Path) -> None:
    report = run_local_corpus(output_dir=tmp_path, write_artifacts=True)

    assert report["status"] == "passed"
    assert (tmp_path / LOCAL_CORPUS_JSON).exists()
    assert (tmp_path / LOCAL_CORPUS_MD).exists()
