"""Per-module coverage floor enforcement.

``pyproject.toml`` enforces a global ``fail_under`` via ``coverage
report``, but coverage at the project level can mask modules that have
regressed sharply. This script reads a parsed ``coverage report`` JSON
output and asserts that each module listed in ``MINIMUMS`` is at or
above its threshold.

Run with ``python3 scripts/check_coverage_floors.py <report.json>``.
The JSON is produced by::

    coverage json -o coverage.json

Add or raise floors as the test suite improves. Lowering a floor
should always be paired with a code comment explaining why.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Per-module minimum coverage (percent, 0-100). Keys are
# ``backend.app.<module>`` paths or glob-style prefixes with ``*``.
MINIMUMS: dict[str, float] = {
    "backend/app/url_safety.py": 60.0,
    "backend/app/storage_interface.py": 70.0,
    "backend/app/routers/jobs.py": 70.0,
    "backend/app/routers/exports.py": 60.0,
    "backend/app/lifespan.py": 40.0,
    # The two Postgres backends are large and the testcontainers
    # lane is opt-in. The floors here are a *floor* not a goal —
    # raise them in tandem with parity tests in test_psycopg3_repository.py
    # / test_postgres_repository.py.
    "backend/app/psycopg3_repository.py": 24.0,
    "backend/app/postgres_repository.py": 24.0,
}


def _match(path: str, key: str) -> bool:
    if key.endswith("*"):
        return path.startswith(key[:-1])
    return path == key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to coverage JSON")
    args = parser.parse_args()
    if not args.report.exists():
        print(f"coverage report not found: {args.report}", file=sys.stderr)
        return 2
    data = json.loads(args.report.read_text())
    files = data.get("files", {})
    failures: list[tuple[str, float, float]] = []
    for key, minimum in MINIMUMS.items():
        for path, info in files.items():
            if _match(path, key):
                # ``coverage json`` emits the percent at ``summary.percent_covered``
                # (not at the top level). Fall back to ``0.0`` for robustness.
                summary = info.get("summary", {})
                covered = float(
                    info.get("percent_covered", summary.get("percent_covered", 0.0)),
                )
                if covered < minimum:
                    failures.append((path, covered, minimum))
                break
        else:
            print(f"warning: no coverage entry matched pattern {key!r}", file=sys.stderr)
    if failures:
        print("Module coverage floors FAILED:", file=sys.stderr)
        for path, covered, minimum in failures:
            print(f"  {path}: {covered:.1f}% < {minimum:.1f}%", file=sys.stderr)
        return 1
    print("Module coverage floors OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
