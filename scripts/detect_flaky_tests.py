#!/usr/bin/env python3
"""Detect flaky tests by running them multiple times.

Usage:
    scripts/detect_flaky_tests.py [--count=3] [--timeout=30]

Runs each test multiple times and reports any tests that don't produce
consistent results (pass/pass or fail/fail).
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"


def run_pytest(test_path: str, count: int, timeout: int) -> dict[str, str]:
    """Run a test multiple times and return results."""
    results = {}
    for i in range(count):
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    test_path,
                    "-x",
                    "-q",
                    f"--timeout={timeout}",
                    "--tb=line",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=timeout + 10,
            )
            results[str(i + 1)] = "pass" if proc.returncode == 0 else "fail"
        except subprocess.TimeoutExpired:
            results[str(i + 1)] = "timeout"
        except Exception as e:
            results[str(i + 1)] = f"error: {e}"
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect flaky tests")
    parser.add_argument("--count", type=int, default=3, help="Number of times to run each test")
    parser.add_argument("--timeout", type=int, default=30, help="Per-test timeout in seconds")
    parser.add_argument(
        "--tests",
        nargs="*",
        help="Specific test files to check (default: all tests)",
    )
    args = parser.parse_args()

    # Discover tests
    if args.tests:
        test_files = args.tests
    else:
        # Run pytest to collect tests
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "--co",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
        test_files = []
        for line in proc.stdout.splitlines():
            if "::" in line and ".py" in line:
                # Extract file path from "file.py::test_name"
                file_path = line.split("::")[0]
                if file_path not in test_files:
                    test_files.append(file_path)

    if not test_files:
        print("No tests found to check")
        return 1

    print(f"Checking {len(test_files)} test files for flakiness ({args.count} runs each)")
    print("=" * 60)

    flaky_tests = []
    consistent_tests = []

    for test_file in test_files:
        print(f"\nChecking: {test_file}")
        results = run_pytest(test_file, args.count, args.timeout)

        # Check for consistency
        result_values = list(results.values())
        if len(set(result_values)) > 1:
            flaky_tests.append((test_file, results))
            print(f"  FLAKY: {results}")
        else:
            consistent_tests.append(test_file)
            print(f"  CONSISTENT: {result_values[0]}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Summary: {len(consistent_tests)} consistent, {len(flaky_tests)} flaky")

    if flaky_tests:
        print("\nFlaky tests found:")
        for test_file, results in flaky_tests:
            print(f"  {test_file}: {results}")

        # Write flaky test report
        report_path = REPO / "docs" / "FLAKY_TESTS.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Flaky Test Report\n\n")
            f.write(f"**Generated:** {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
            f.write("## Flaky Tests\n\n")
            f.write("| Test File | Run 1 | Run 2 | Run 3 |\n")
            f.write("|-----------|-------|-------|-------|\n")
            for test_file, results in flaky_tests:
                r1 = results.get("1", "N/A")
                r2 = results.get("2", "N/A")
                r3 = results.get("3", "N/A")
                f.write(f"| `{test_file}` | {r1} | {r2} | {r3} |\n")
            f.write("\n## Action Required\n\n")
            f.write("1. Review flaky tests and identify root cause\n")
            f.write("2. Fix or mark with `@pytest.mark.flaky`\n")
            f.write("3. Re-run this script to verify fix\n")

        print(f"\nFlaky test report written to {report_path}")
        return 1
    print("\nNo flaky tests detected!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
