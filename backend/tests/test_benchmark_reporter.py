"""Unit Tests for Phase 84 Automated Benchmark Reporting."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import pytest
from app.benchmark_reporter import BenchmarkReporter, BenchmarkRun

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def benchmark_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Set up an isolated benchmark directory per test.

    Uses ``tmp_path`` so tests never share a database file, eliminating
    the ordering flake that occurred when ``test_db_initialization`` ran
    after other tests had already created (or torn down) the shared DB.
    """
    db_path = str(tmp_path / "benchmark.db")
    dashboard_path = str(tmp_path / "regression_dashboard.md")
    monkeypatch.setattr("app.benchmark_reporter.DASHBOARD_PATH", dashboard_path)
    return db_path


def test_db_initialization(benchmark_env: str) -> None:
    BenchmarkReporter(db_path=benchmark_env)
    assert os.path.exists(benchmark_env)


def test_record_run(benchmark_env: str) -> None:
    reporter = BenchmarkReporter(db_path=benchmark_env)
    run = BenchmarkRun(
        run_id="run-1",
        timestamp=time.time(),
        precision=0.95,
        recall=0.90,
        fallback_rate=0.10,
        latency_ms=1200.0,
        failed_selectors=["#price", ".rating"],
    )

    comparison = reporter.record_run(run)
    assert comparison["status"] == "stable"

    history = reporter.get_history(limit=5)
    assert len(history) == 1
    assert history[0].run_id == "run-1"
    assert sorted(history[0].failed_selectors) == sorted(["#price", ".rating"])


def test_regression_alert_trigger(benchmark_env: str) -> None:
    reporter = BenchmarkReporter(db_path=benchmark_env)

    # Record strong historic runs
    for i in range(3):
        reporter.record_run(
            BenchmarkRun(
                run_id=f"hist-{i}",
                timestamp=time.time() - 3600 * (3 - i),
                precision=0.98,
                recall=0.96,
                fallback_rate=0.02,
                latency_ms=800.0,
            ),
        )

    # Record a degraded run
    degraded = BenchmarkRun(
        run_id="degraded-1",
        timestamp=time.time(),
        precision=0.90,  # 8% drop (regression threshold is 5%)
        recall=0.95,
        fallback_rate=0.15,
        latency_ms=1500.0,
    )

    comparison = reporter.record_run(degraded)
    assert comparison["status"] == "regression"
    assert "ALERT: Regression detected!" in comparison["message"]
    assert comparison["precision_drift"] < -0.05


def test_dashboard_generation(benchmark_env: str) -> None:
    reporter = BenchmarkReporter(db_path=benchmark_env)
    run = BenchmarkRun(
        run_id="dashboard-run",
        timestamp=time.time(),
        precision=0.92,
        recall=0.88,
        fallback_rate=0.08,
        latency_ms=950.0,
    )
    reporter.record_run(run)

    from app.benchmark_reporter import DASHBOARD_PATH

    assert os.path.exists(DASHBOARD_PATH)
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        content = f.read()

    assert "dashboard-run" in content
    assert "DataForge Regression Trends" in content
