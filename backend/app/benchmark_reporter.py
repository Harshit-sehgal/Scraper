"""Benchmark Reporter — continuous operational intelligence for tracking precision / recall regressions.

Provides:
  - SQLite persistence for historical benchmark runs.
  - Automated precision / recall regression trend calculations.
  - Automatic alerts for regressions crossing critical thresholds (> 5%).
  - Markdown-based auto-updating regression dashboard logs.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(_BACKEND_ROOT / "data" / "benchmarks" / "benchmark_history.db")
DASHBOARD_PATH = str(_BACKEND_ROOT / "data" / "benchmarks" / "regression_dashboard.md")


@dataclass
class BenchmarkRun:
    """Represents a single benchmark run snapshot."""

    run_id: str
    timestamp: float
    precision: float
    recall: float
    fallback_rate: float
    latency_ms: float
    failed_selectors: list[str] = field(default_factory=list)


class BenchmarkReporter:
    """Manages the persistence, delta comparison, and reporting of benchmark metrics."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite benchmark reporting database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    precision REAL NOT NULL,
                    recall REAL NOT NULL,
                    fallback_rate REAL NOT NULL,
                    latency_ms REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS run_failures (
                    run_id TEXT,
                    selector TEXT,
                    FOREIGN KEY(run_id) REFERENCES benchmark_runs(run_id)
                )
            """)
            conn.commit()

    def record_run(self, run: BenchmarkRun) -> dict[str, Any]:
        """Record a benchmark run and check for regressions against previous averages."""
        comparison = self.compare_against_history(run.precision, run.recall)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO benchmark_runs VALUES (?, ?, ?, ?, ?, ?)",
                (run.run_id, run.timestamp, run.precision, run.recall, run.fallback_rate, run.latency_ms),
            )
            for selector in run.failed_selectors:
                conn.execute("INSERT INTO run_failures VALUES (?, ?)", (run.run_id, selector))
            conn.commit()

        # Update the visual regression dashboard
        try:
            self.generate_dashboard()
        except Exception as e:
            logger.warning("[Reporter] Failed to update regression dashboard: %s", e)

        return comparison

    def compare_against_history(self, current_precision: float, current_recall: float) -> dict[str, Any]:
        """Compare current precision / recall against historical averages."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(precision), AVG(recall) FROM benchmark_runs")
            row = cursor.fetchone()

        avg_precision, avg_recall = row or (None, None)
        if avg_precision is None or avg_recall is None:
            return {
                "status": "stable",
                "precision_drift": 0.0,
                "recall_drift": 0.0,
                "message": "First recorded benchmark run.",
            }

        precision_drift = current_precision - avg_precision
        recall_drift = current_recall - avg_recall

        status = "stable"
        message = "Metrics are stable compared to historical averages."

        if precision_drift < -0.05 or recall_drift < -0.05:
            status = "regression"
            message = f"ALERT: Regression detected! Precision drift: {precision_drift:+.2%}, Recall drift: {recall_drift:+.2%}"
            logger.warning("[Reporter] %s", message)

        return {
            "status": status,
            "precision_drift": round(precision_drift, 4),
            "recall_drift": round(recall_drift, 4),
            "message": message,
        }

    def get_history(self, limit: int = 10) -> list[BenchmarkRun]:
        """Retrieve recent benchmark runs from the persistent store."""
        runs = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT run_id, timestamp, precision, recall, fallback_rate, latency_ms "
                "FROM benchmark_runs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            for row in cursor.fetchall():
                run_id = row[0]
                fail_cursor = conn.cursor()
                fail_cursor.execute("SELECT selector FROM run_failures WHERE run_id = ?", (run_id,))
                failures = [r[0] for r in fail_cursor.fetchall()]

                runs.append(
                    BenchmarkRun(
                        run_id=row[0],
                        timestamp=row[1],
                        precision=row[2],
                        recall=row[3],
                        fallback_rate=row[4],
                        latency_ms=row[5],
                        failed_selectors=failures,
                    ),
                )
        return runs

    def generate_dashboard(self) -> None:
        """Generate / overwrite the auto-updating markdown dashboard file."""
        history = self.get_history(limit=5)
        if not history:
            return

        Path(DASHBOARD_PATH).parent.mkdir(parents=True, exist_ok=True)

        with Path(DASHBOARD_PATH).open("w", encoding="utf-8") as f:
            f.write("# 📊 DataForge Regression Trends & Benchmarks Dashboard\n\n")
            f.write("> **Continuous Operational Intelligence**: Auto-updating regression trends tracker.\n\n")
            f.write("## 1. Recent Execution Runs\n\n")
            f.write("| Run ID | Date & Time | Precision | Recall | Fallback Rate | Avg Latency | Failed Selectors |\n")
            f.write("| :--- | :--- | :---: | :---: | :---: | :---: | :--- |\n")

            for run in history:
                date_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(run.timestamp))
                failed_str = ", ".join(run.failed_selectors) if run.failed_selectors else "None"
                f.write(
                    f"| `{run.run_id}` | {date_str} | **{run.precision:.2%}** | **{run.recall:.2%}** | "
                    f"{run.fallback_rate:.2%} | {run.latency_ms:.0f}ms | {failed_str} |\n",
                )

            # Add simple visual progress indicators
            f.write("\n## 2. Dynamic Performance Indicators\n\n")
            latest = history[0]
            f.write(
                f"- **Latest Extraction Success (Precision)**: `{'█' * int(latest.precision * 20)}{
                    '░' * (20 - int(latest.precision * 20))
                }` ({latest.precision:.2%})\n",
            )
            f.write(
                f"- **Latest Capture Rate (Recall)**: `{'█' * int(latest.recall * 20)}{'░' * (20 - int(latest.recall * 20))}` ({
                    latest.recall:.2%})\n",
            )
            f.write(f"- **Latest Fallback Rate**: `{latest.fallback_rate:.2%}`\n")
            f.write(f"- **Latest Average Scrape Latency**: `{latest.latency_ms:.0f}ms`\n\n")

            f.write("---\n * End of Auto-Generated Dashboard Log.*\n")
