"""Benchmark trend tracking.

Persists per-run aggregate metrics to a JSONL file under
``artifacts/benchmarks/trends.jsonl``. Provides regression detection by
comparing the current run's metrics against a trailing window.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TRENDS_PATH = REPO_ROOT / "artifacts" / "benchmarks" / "trends.jsonl"


def record_benchmark_run(report: dict[str, Any], path: Path = TRENDS_PATH) -> Path:
    """Append an aggregate record to the trends file.

    Writes one JSONL line per call: ``{timestamp, version, aggregate}``.
    Returns the path that was written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "version": report.get("version"),
        "aggregate": report.get("aggregate"),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def latest_aggregate_trend(n: int = 10, path: Path = TRENDS_PATH) -> list[dict[str, Any]]:
    """Read last N aggregate records (most recent first) from trends file."""
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records: list[dict[str, Any]] = []
    for line in lines[-n:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def detect_regression(
    current: dict[str, float],
    history: list[dict[str, Any]],
    *,
    threshold: float = 0.02,
    min_history: int = 3,
) -> list[str]:
    """Return list of metric names where current drops > threshold below history mean.

    ``current`` maps metric_name -> value. ``history`` is a list of
    records as returned by :func:`latest_aggregate_trend`; their
    ``aggregate`` sub-dicts are averaged across the window. Metrics
    with insufficient history (fewer than ``min_history`` records) are
    skipped, so cold starts don't trigger spurious regressions.
    """
    if len(history) < min_history:
        return []

    keys = set(current.keys())
    for record in history:
        agg = record.get("aggregate") or {}
        keys &= set(agg.keys())
    if not keys:
        return []

    regressions: list[str] = []
    for key in sorted(keys):
        history_values = [float(record["aggregate"][key]) for record in history if key in record.get("aggregate", {})]
        if len(history_values) < min_history:
            continue
        baseline = sum(history_values) / len(history_values)
        current_value = float(current.get(key, baseline))
        if baseline - current_value > threshold:
            regressions.append(
                f"{key} dropped from baseline {baseline:.4f} to {current_value:.4f} "
                f"(delta={current_value - baseline:.4f}, threshold={threshold})"
            )
    return regressions
