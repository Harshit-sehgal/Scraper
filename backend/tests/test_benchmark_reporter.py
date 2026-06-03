"""
Unit Tests for Phase 84 Automated Benchmark Reporting.
"""

from __future__ import annotations

import os
import time

import pytest
from app.benchmark_reporter import DASHBOARD_PATH, DB_PATH, BenchmarkReporter, BenchmarkRun


def _clean_benchmark_db_files() -> None:
    """Remove benchmark DB and dashboard files along with any WAL / SHM journal files."""
    for path in [DB_PATH, DASHBOARD_PATH]:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    # Also clean up WAL / SHM journal files for DB_PATH
    base = DB_PATH
    for suffix in ["-wal", "-shm", "-journal"]:
        try:
            os.remove(base + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture(autouse=True)
def clean_benchmark_env():
    # Remove existing files if any (including WAL / SHM journal files)
    _clean_benchmark_db_files()
    yield
    # Cleanup files after test run
    _clean_benchmark_db_files()


def test_db_initialization() -> None:
    BenchmarkReporter()
    assert os.path.exists(DB_PATH)


def test_record_run() -> None:
    reporter = BenchmarkReporter()
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


def test_regression_alert_trigger() -> None:
    reporter = BenchmarkReporter()

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
            )
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


def test_dashboard_generation() -> None:
    reporter = BenchmarkReporter()
    run = BenchmarkRun(
        run_id="dashboard-run", timestamp=time.time(), precision=0.92, recall=0.88, fallback_rate=0.08, latency_ms=950.0
    )
    reporter.record_run(run)

    assert os.path.exists(DASHBOARD_PATH)
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    assert "dashboard-run" in content
    assert "DataForge Regression Trends" in content
