"""Anti-Bot Headless Detection Benchmark (Anti 33).

Standalone runner (NOT a test) that launches a Playwright browser with
DataForge stealth settings and runs 15+ detection checks.  Generates a
JSON report with pass/warn/fail per check.

Runs fully offline - all checks are evaluated against the browser
context itself, no external URLs are needed.

Usage::

    python -m backend.benchmarks.test_anti_bot_detection_benchmark \\
        --output report.json

The returned JSON is a structured report suitable for CI gates or
operator dashboards.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

# Allow running this file directly (without -m)
_BENCH_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _BENCH_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

try:
    from app.browser_pool import (
        BrowserPool,
        reset_global_browser_pool,
        run_headless_detection_checks,
    )
    from app.config import settings
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(f"[benchmark] Import error: {exc}\n")
    sys.stderr.write("[benchmark] Run from backend/ directory or with PYTHONPATH=backend\n")
    sys.exit(2)


# ── Benchmark Logic ────────────────────────────────────────────────────


async def _run_benchmark(
    *,
    network_check: bool = False,
) -> dict[str, Any]:
    """Launch Playwright with stealth and run detection checks."""
    pool = BrowserPool()
    started_at = time.time()
    report: dict[str, Any] = {
        "started_at": started_at,
        "settings": {
            "headless": settings.PLAYWRIGHT_HEADLESS,
            "stealth_enabled": settings.PLAYWRIGHT_STEALTH,
            "security_hardening": settings.BROWSER_SECURITY_HARDENING,
        },
        "checks": [],
    }

    try:
        # Build an isolated context so we don't interfere with anything else.
        async with pool.acquire_context() as (_ctx_id, context):
            # Run checks against the context itself
            report["checks_result"] = await run_headless_detection_checks(context)

            # Optional online check — could be turned on if a network is available
            if network_check:
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get("https://bot.sannysoft.com/")
                        report["online_check"] = {
                            "url": "https://bot.sannysoft.com/",
                            "status_code": resp.status_code,
                            "snippet": resp.text[:500],
                        }
                except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                    report["online_check"] = {"error": str(exc)}
    finally:
        with contextlib.suppress(RuntimeError, OSError, ValueError, TypeError):
            await pool.close()
        reset_global_browser_pool()

    report["elapsed_seconds"] = round(time.time() - started_at, 2)
    report["overall"] = "PASS" if report.get("checks_result", {}).get("score", 0) >= 70 else "WARN"
    return report


def _format_text_report(report: dict[str, Any]) -> str:
    """Render the JSON report as a human-readable summary."""
    lines = [
        "Anti-Bot Detection Benchmark",
        "============================",
        f"Overall: {report.get('overall', 'UNKNOWN')}     Score: {report.get('checks_result', {}).get('score', 0)}",
        "",
    ]
    summary = report.get("checks_result", {}).get("summary", {})
    lines.append(
        f"Summary: {summary.get('pass', 0)} pass, "
        f"{summary.get('warn', 0)} warn, "
        f"{summary.get('fail', 0)} fail  (total: {summary.get('total', 0)})"
    )
    lines.append("")
    for c in report.get("checks_result", {}).get("checks", []):
        marker = {"pass": "OK  ", "warn": "WARN", "fail": "FAIL"}.get(c["status"], "????")
        lines.append(f"  [{marker}] {c['name']:35s}  {c['detail']}")
    lines.append("")
    lines.append(f"Elapsed: {report.get('elapsed_seconds', '?')}s")
    return "\n".join(lines)


# ── CLI Entry Point ────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Anti-bot headless detection benchmark",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="anti_bot_detection_report.json",
        help="Path to write JSON report (default: anti_bot_detection_report.json)",
    )
    parser.add_argument(
        "--with-online-check",
        action="store_true",
        help="Also run an online detection-page probe (requires network)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable summary output (JSON only)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = asyncio.run(_run_benchmark(network_check=args.with_online_check))
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        sys.stderr.write(f"[benchmark] Fatal error: {exc}\n")
        return 1

    # Write JSON
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str))

    if not args.quiet:
        sys.stdout.write(_format_text_report(report) + "\n")
        sys.stdout.write(f"\nJSON report: {output_path}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
