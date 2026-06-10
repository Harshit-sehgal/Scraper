#!/usr/bin/env python3
"""Generate detailed coverage report with gap analysis.

Usage:
    scripts/generate_coverage_report.py [--fail-under=60]

Generates coverage report and identifies modules below threshold.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"

# Coverage thresholds per module (can be adjusted)
MODULE_THRESHOLDS = {
    "app/routers": 70,
    "app/services": 65,
    "app/utils": 60,
    "app/auth": 75,
    "app/config": 50,
}


def run_coverage(fail_under: int) -> dict:
    """Run pytest with coverage and return results."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=backend/app",
            "--cov-report=json:coverage.json",
            "--cov-report=term-missing",
            f"--cov-fail-under={fail_under}",
            "-q",
            "--tb=short",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Parse coverage.json
    coverage_file = REPO / "coverage.json"
    if coverage_file.exists():
        with open(coverage_file, encoding="utf-8") as f:
            coverage_data = json.load(f)
    else:
        coverage_data = {}

    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "coverage": coverage_data,
    }


def analyze_coverage_gaps(coverage_data: dict) -> list[dict]:
    """Identify modules below threshold."""
    gaps = []
    files = coverage_data.get("files", {})

    for file_path, file_data in files.items():
        # Normalize path
        rel_path = file_path.replace("backend/", "")

        # Check against thresholds
        for module, threshold in MODULE_THRESHOLDS.items():
            if module in rel_path:
                coverage_pct = file_data.get("summary", {}).get("percent_covered", 0)
                if coverage_pct < threshold:
                    gaps.append(
                        {
                            "file": rel_path,
                            "coverage": coverage_pct,
                            "threshold": threshold,
                            "missing": file_data.get("missing_lines", []),
                        },
                    )
                break

    return gaps


def generate_report(coverage_data: dict, gaps: list[dict]) -> str:
    """Generate markdown report."""
    total = coverage_data.get("totals", {})
    percent_covered = total.get("percent_covered", 0)
    covered_lines = total.get("covered_lines", 0)
    total_lines = total.get("num_statements", 0)

    lines = [
        "# Coverage Report",
        "",
        f"**Generated:** {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## Summary",
        "",
        f"- **Total Coverage:** {percent_covered:.1f}%",
        f"- **Lines Covered:** {covered_lines:,} / {total_lines:,}",
        f"- **Coverage Gaps:** {len(gaps)} modules below threshold",
        "",
    ]

    if gaps:
        lines.extend(
            [
                "## Coverage Gaps",
                "",
                "| Module | Coverage | Threshold | Status |",
                "|--------|----------|-----------|--------|",
            ],
        )
        for gap in sorted(gaps, key=lambda x: x["coverage"]):
            status = "⚠️ Below threshold" if gap["coverage"] < gap["threshold"] else "✅"
            lines.append(
                f"| `{gap['file']}` | {gap['coverage']:.1f}% | {gap['threshold']}% | {status} |",
            )

        lines.extend(
            [
                "",
                "## Recommendations",
                "",
                "1. Add tests for modules below threshold",
                "2. Focus on critical paths first (routers, services)",
                "3. Use `# pragma: no cover` for intentionally uncovered code",
                "4. Update MODULE_THRESHOLDS in this script as coverage improves",
            ],
        )
    else:
        lines.extend(["## Coverage Gaps", "", "No modules below threshold! 🎉"])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate coverage report")
    parser.add_argument(
        "--fail-under",
        type=int,
        default=60,
        help="Minimum coverage percentage required",
    )
    args = parser.parse_args()

    print("Running coverage analysis...")
    result = run_coverage(args.fail_under)

    if not result["coverage"]:
        print("No coverage data generated. Check test run output.")
        print(result["stdout"])
        if result["stderr"]:
            print("STDERR:", result["stderr"])
        return 1

    gaps = analyze_coverage_gaps(result["coverage"])
    report = generate_report(result["coverage"], gaps)

    # Write report
    report_path = REPO / "docs" / "COVERAGE_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nCoverage report written to {report_path}")
    print(f"Total coverage: {result['coverage'].get('totals', {}).get('percent_covered', 0):.1f}%")
    print(f"Coverage gaps: {len(gaps)} modules below threshold")

    # Print summary
    if gaps:
        print("\nModules below threshold:")
        for gap in gaps[:10]:  # Show top 10
            print(f"  {gap['file']}: {gap['coverage']:.1f}% (threshold: {gap['threshold']}%)")

    return 0 if result["returncode"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
