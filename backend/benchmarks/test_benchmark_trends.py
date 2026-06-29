"""Tests for benchmark trend tracking infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import benchmark_trends


def test_trends_file_append(tmp_path: Path) -> None:
    target = tmp_path / "trends.jsonl"
    report = {
        "version": "2026-06-29.local-corpus.v6",
        "aggregate": {"row_f1": 0.95, "field_f1": 0.97, "case_count": 25},
    }

    written = benchmark_trends.record_benchmark_run(report, path=target)

    assert written == target
    assert target.exists()
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["version"] == "2026-06-29.local-corpus.v6"
    assert record["aggregate"]["row_f1"] == 0.95
    assert "timestamp" in record


def test_trends_file_append_multiple(tmp_path: Path) -> None:
    target = tmp_path / "trends.jsonl"
    for i in range(3):
        benchmark_trends.record_benchmark_run(
            {"version": f"v{i}", "aggregate": {"row_f1": 0.9 + i * 0.01, "case_count": 10}},
            path=target,
        )

    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert [r["version"] for r in records] == ["v0", "v1", "v2"]


def test_latest_10_records_readback(tmp_path: Path) -> None:
    target = tmp_path / "trends.jsonl"
    for i in range(15):
        benchmark_trends.record_benchmark_run(
            {"version": f"v{i}", "aggregate": {"row_f1": float(i) / 100, "case_count": 5}},
            path=target,
        )

    latest = benchmark_trends.latest_aggregate_trend(n=10, path=target)
    assert len(latest) == 10
    # Oldest-first ordering: v5, v6, ..., v14
    assert latest[0]["version"] == "v5"
    assert latest[-1]["version"] == "v14"


def test_latest_trend_returns_empty_when_no_file(tmp_path: Path) -> None:
    target = tmp_path / "missing.jsonl"
    assert benchmark_trends.latest_aggregate_trend(path=target) == []


def test_latest_trend_skips_malformed_lines(tmp_path: Path) -> None:
    target = tmp_path / "trends.jsonl"
    target.write_text(
        "\n".join(
            [
                json.dumps({"version": "v1", "aggregate": {"row_f1": 1.0}}),
                "this is not valid json",
                json.dumps({"version": "v2", "aggregate": {"row_f1": 0.9}}),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    latest = benchmark_trends.latest_aggregate_trend(path=target)
    assert len(latest) == 2
    assert [r["version"] for r in latest] == ["v1", "v2"]


def test_no_false_regression_on_identical_scores() -> None:
    """When current and history are identical, no regressions are flagged."""
    history = [
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0, "case_count": 25}},
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0, "case_count": 25}},
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0, "case_count": 25}},
    ]
    current = {"row_f1": 1.0, "field_f1": 1.0, "case_count": 25}
    assert benchmark_trends.detect_regression(current, history) == []


def test_regression_detected_when_score_drops() -> None:
    """A 0.05 drop exceeds the 0.02 default threshold."""
    history = [
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0}},
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0}},
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0}},
    ]
    current = {"row_f1": 0.93, "field_f1": 1.0}
    regressions = benchmark_trends.detect_regression(current, history)
    assert any("row_f1" in r for r in regressions)
    assert not any("field_f1" in r for r in regressions)


def test_no_regression_with_insufficient_history() -> None:
    """Cold start: less than 3 history records → no regressions flagged."""
    history = [{"aggregate": {"row_f1": 1.0}}]
    current = {"row_f1": 0.5}
    assert benchmark_trends.detect_regression(current, history) == []


def test_regression_skips_metrics_with_partial_history() -> None:
    """A metric appearing in only some history records is skipped, not crash."""
    history = [
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0}},
        {"aggregate": {"row_f1": 1.0}},  # no field_f1
        {"aggregate": {"row_f1": 1.0, "field_f1": 1.0}},
    ]
    current = {"row_f1": 0.5, "field_f1": 0.5}
    regressions = benchmark_trends.detect_regression(current, history)
    # row_f1 is in all 3 records; field_f1 is in only 2 → skipped
    assert any("row_f1" in r for r in regressions)
    assert not any("field_f1" in r for r in regressions)


def test_regression_drop_below_threshold_not_flagged() -> None:
    """A 0.01 drop is within the 0.02 default threshold → not a regression."""
    history = [
        {"aggregate": {"row_f1": 1.0}},
        {"aggregate": {"row_f1": 1.0}},
        {"aggregate": {"row_f1": 1.0}},
    ]
    current = {"row_f1": 0.99}
    assert benchmark_trends.detect_regression(current, history) == []


def test_round_trip_with_actual_corpus(tmp_path: Path) -> None:
    """End-to-end: write a real local corpus report, read it back, detect nothing."""
    from benchmarks.local_corpus import run_local_corpus

    report = run_local_corpus(write_artifacts=False)
    target = tmp_path / "trends.jsonl"
    benchmark_trends.record_benchmark_run(report, path=target)
    latest = benchmark_trends.latest_aggregate_trend(path=target)
    assert len(latest) == 1
    assert latest[0]["aggregate"]["case_count"] == 25
    # Single-record history is below min_history → no regression detection
    assert benchmark_trends.detect_regression(report["aggregate"], latest) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
