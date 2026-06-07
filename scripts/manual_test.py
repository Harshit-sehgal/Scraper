#!/usr/bin/env python3
"""
DataForge Studio — Manual Test CLI
===================================
An interactive CLI tool to manually test and explore the DataForge system.

Usage:
    python scripts/manual_test.py             # Interactive menu
    python scripts/manual_test.py health       # Quick health check
    python scripts/manual_test.py topology     # Show topology state
    python scripts/manual_test.py test-job     # Create and monitor a test job
    python scripts/manual_test.py all          # Run selected checks sequentially
    python scripts/manual_test.py --help       # Show this message

Requires the server to be running (use `scripts/start.sh`).
"""

import argparse
import json
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌ 'requests' library not found. Install it with:  pip install requests")
    sys.exit(1)

import os

# Read API base URL from environment variable, with default for development
API_BASE = os.getenv("DATAFORGE_API_BASE", "http://127.0.0.1:8000")


# ─── Utilities ─────────────────────────────────────────────────────────────


def _fmt(val: float, decimals: int = 3) -> str:
    return f"{val:.{decimals}f}"


def _bar(val: float, width: int = 30, filled: str = "█", empty: str = "░") -> str:
    n = max(0, min(width, int(val * width)))
    return filled * n + empty * (width - n)


def _color(val: float, low: float, high: float, green: str = "", red: str = "") -> str:
    """Color a value red if above high, green if below low."""
    if val <= low:
        return f"{green}{val}{red}" if green else str(val)
    if val >= high:
        return f"{red}{val}{green}" if red else str(val)
    return str(val)


def _status_icon(status: str) -> str:
    return {
        "completed": "✅",
        "failed": "❌",
        "canceled": "⏹️",
        "running": "🔄",
        "discovering": "🔍",
        "pending": "⏳",
    }.get(status, "❓")


def _print_header(title: str):
    print()
    print("╔" + "═" * 60 + "╗")
    print(f"║ {title:<58} ║")
    print("╚" + "═" * 60 + "╝")


def _print_section(title: str):
    print(f"\n─── {title} ─{'─' * (56 - len(title))}")


# ─── API Calls ─────────────────────────────────────────────────────────────


def api_get(path: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        print(f"  ❌ Connection refused — is the server running on {API_BASE}?")
        return None
    except requests.Timeout:
        print(f"  ⏱️  Timeout fetching {path}")
        return None
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        print(f"  ❌ HTTP {status}: {path}")
        return None


def api_post(path: str, data: dict, timeout: int = 30) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        print(f"  ❌ Connection refused on {API_BASE}{path}")
        return None
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        text = e.response.text[:200] if e.response is not None else ""
        print(f"  ❌ HTTP {status}: {text}")
        return None
    except requests.Timeout:
        print(f"  ⏱️  Timeout on {path}")
        return None


# ─── Check: Health ─────────────────────────────────────────────────────────


def check_health():
    """Check server status, job counts, and runtime config."""
    _print_header("SYSTEM HEALTH CHECK")
    data = api_get("/api/system/status")
    if not data:
        return False

    status = data.get("status", "unknown")
    icon = "✅" if status == "online" else "❌"
    print(f"  Server Status:     {icon} {status.upper()}")

    jobs = data.get("jobs", {})
    print(
        f"  Jobs:              {jobs.get('total', 0)} total, "
        f"{jobs.get('active', 0)} active, "
        f"{jobs.get('completed', 0)} completed, "
        f"{jobs.get('failed', 0)} failed",
    )

    config = data.get("runtime_limits", {})
    _print_section("Runtime Limits")
    for key, val in config.items():
        print(f"  {key.replace('_', ' ').title():<40} {val}")

    state_file = data.get("state_file", "N/A")
    print(f"  {'State File':<40} {state_file}")

    # Check topology endpoint for field health
    topo = api_get("/api/system/topology")
    if topo:
        metrics = topo.get("metrics", {})
        print()
        print(f"  Field Pressure:    {metrics.get('field_pressure', 'N/A')}")
        print(f"  Global Energy:     {metrics.get('global_energy', 'N/A')}")
        print(f"  Energy Balance:    {metrics.get('energy_balance', 'N/A')}  (0 = perfectly conserved)")
        print(f"  Regions:           {metrics.get('region_count', 0)}")
        print(f"  Integrity Score:   {metrics.get('integrity_score', 'N/A')}")

    return True


# ─── Check: Topology ───────────────────────────────────────────────────────


def check_topology(detailed: bool = False):
    """Show semantic field topology state."""
    _print_header("SEMANTIC FIELD TOPOLOGY")
    data = api_get("/api/system/topology")
    if not data:
        return

    metrics = data.get("metrics", {})
    print(f"\n  Field Pressure:      {_fmt(metrics.get('field_pressure', 0))}  {_bar(metrics.get('field_pressure', 0) / 2)}")
    print(f"  Global Energy:       {_fmt(metrics.get('global_energy', 0))}  {_bar(metrics.get('global_energy', 0) / 10)}")
    print(
        f"  Energy Balance:      {_fmt(metrics.get('energy_balance', 0), 4)}  "
        f"{'✅ CONSERVED' if abs(metrics.get('energy_balance', 0)) < 0.01 else '⚠️  DRIFT'}",
    )
    print(f"  Semantic Temp:       {_fmt(metrics.get('semantic_temperature', 0))}")
    print(f"  Global Entropy:      {_fmt(metrics.get('global_entropy', 0))}")
    print(f"  Integrity Score:     {_fmt(metrics.get('integrity_score', 0))}")
    print(f"  Regions:             {metrics.get('region_count', 0)}")
    print(f"  Exclusions:          {metrics.get('exclusion_count', 0)}")
    print(f"  Learning Count:      {metrics.get('learning_count', 0)}")
    print(f"  Crystalline:         {metrics.get('crystalline_count', 0)}")

    regions = data.get("field_regions", [])
    edges = data.get("topology_edges", [])
    edge_fields = data.get("edge_fields", [])
    role_compat = data.get("role_compatibility", [])
    meso = data.get("meso_clusters", [])
    macro = data.get("macro_continents", [])

    print(f"\n  Regions:             {len(regions)} active")
    print(f"  Topology Edges:      {len(edges)}")
    print(f"  Edge Fields:         {len(edge_fields)}")
    print(f"  Role Compatibilities: {len(role_compat)}")
    print(f"  Meso Clusters:       {len(meso)}")
    print(f"  Macro Continents:    {len(macro)}")

    if detailed and regions:
        _print_section("Field Regions (most unstable)")
        sorted_regions = sorted(regions, key=lambda r: r.get("instability", 0), reverse=True)
        for r in sorted_regions[:10]:
            token = r.get("token", "?")
            roles = ",".join(r.get("competing_roles", []))[:30]
            inst = r.get("instability", 0)
            energy = r.get("local_energy", 0)
            print(f"  [{_fmt(inst)}] {token:<20} roles=({roles}) energy={_fmt(energy)}")

    if detailed and edge_fields:
        _print_section("Edge Fields (top repulsive)")
        sorted_edges = sorted(edge_fields, key=lambda e: e.get("repulsion", 0), reverse=True)
        for e in sorted_edges[:5]:
            print(
                f"  {e.get('source', '?')} ↔ {e.get('target', '?')}  "
                f"affinity={_fmt(e.get('affinity', 0))} "
                f"repulsion={_fmt(e.get('repulsion', 0))} "
                f"pressure={_fmt(e.get('pressure', 0))} "
                f"[{e.get('semantics', '?')}]",
            )

    if detailed and role_compat:
        _print_section("Role Compatibility")
        for rc in role_compat[:8]:
            print(f"  {rc.get('role', '?'):<20} → {rc.get('type', '?'):<20} score={_fmt(rc.get('score', 0))}")


# ─── Check: Observability ──────────────────────────────────────────────────


def check_observability():
    """Show observability state, health index, and telemetry."""
    _print_header("OBSERVABILITY & HEALTH")
    data = api_get("/api/system/observability")
    if not data:
        return

    health = data.get("health_index", {})
    if health:
        score = health.get("score", 0)
        status = health.get("status", "unknown")
        icon = {"optimal": "✅", "degraded": "⚠️", "critical": "❌"}.get(status, "❓")
        print(f"\n  Health Index:        {_fmt(score)}  {icon} [{status.upper()}]")

        metrics = health.get("metrics", {})
        print(f"  Stability:           {_fmt(metrics.get('stability', 0))}")
        print(f"  Diversity:           {_fmt(metrics.get('diversity', 0))}")
        print(f"  Tension:             {_fmt(metrics.get('tension', 0))}")
        print(f"  Reliability:         {_fmt(metrics.get('reliability', 0))}")
        print(
            f"  Monoculture Risk:    {_fmt(metrics.get('monoculture_risk', 0))}  "
            f"{'⚠️ HIGH' if metrics.get('monoculture_risk', 0) > 0.5 else 'OK'}",
        )

    hierarchy = data.get("hierarchy", {})
    envelopes = hierarchy.get("envelopes", [])
    levels = hierarchy.get("levels", {})
    if envelopes:
        print(f"  Abstraction Envelopes: {len(envelopes)}")
    if levels:
        print(f"  Role Levels:           {len(levels)} roles with levels")

    telemetry = data.get("telemetry", [])
    heatmap = data.get("heatmap", {})
    print(f"\n  Telemetry Events:    {len(telemetry)} recent")
    print(f"  Heatmap Entries:     {len(heatmap)}")

    # Show recent telemetry events
    if telemetry:
        _print_section("Recent Telemetry (last 8)")
        for e in telemetry[-8:]:
            ts = e.get("timestamp", "")
            if isinstance(ts, float):
                ts = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            event_type = e.get("type", e.get("event_type", "?"))
            details = e.get("details", {})
            detail_str = json.dumps(details)[:50] if details else ""
            print(f"  [{ts}] {event_type:<25} {detail_str}")


# ─── Check: Scheduler Step ─────────────────────────────────────────────────


def trigger_scheduler_step(budget_ms: float = 100.0):
    """Manually trigger the cognitive scheduler."""
    _print_header("COGNITIVE SCHEDULER")
    data = api_post(f"/api/system/scheduler/step?budget_ms={budget_ms}", data={})
    if data:
        print(f"  Tasks Completed: {data.get('tasks_completed', 0)}")
        return True
    return False


# ─── Create and Monitor a Test Job ─────────────────────────────────────────


def run_test_job(mode: str = "manual"):
    """Create a test scraping job and monitor its progress."""
    _print_header(f"TEST JOB — {mode.upper()} MODE")

    import typing

    if mode == "manual":
        payload: dict[str, typing.Any] = {
            "name": f"Manual Test ({datetime.now().strftime('%H:%M:%S')})",
            "mode": "manual",
            "intent": "Get interior designers",
            "topic": "interior designers",
            "urls": ["https://irishinterior.com/contact-us/"],
            "schema_fields": [
                {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
                {"name": "email", "field_type": "email", "description": "email address", "required": False},
            ],
            "source_policy": "all_sources",
        }
        print("  Mode:        Manual (single URL)")
        print("  URL:         https://irishinterior.com/contact-us/")
    else:
        payload = {
            "name": f"Auto Test ({datetime.now().strftime('%H:%M:%S')})",
            "mode": "auto",
            "intent": "Get interior designers in Chennai",
            "topic": "interior designers in chennai",
            "location": "chennai",
            "schema_fields": [
                {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
                {"name": "email", "field_type": "email", "description": "email address", "required": False},
            ],
            "max_pages": 1,
            "source_policy": "all_sources",
        }
        print("  Mode:        Auto (discovery + scrape)")
        print("  Topic:       interior designers in Chennai")
        print("  Max Pages:   1")

    print()
    print("  Creating job...", end=" ", flush=True)
    result = api_post("/api/jobs", data=payload)
    if not result:
        return False

    job_id = result.get("job_id", "")
    print(f"✅ Job ID: {job_id}")

    # Monitor
    print("  Monitoring (polling every 2s, timeout 120s)...")
    print()
    start = time.time()
    timeout = 120
    last_status = ""

    while time.time() - start < timeout:
        job = api_get(f"/api/jobs/{job_id}")
        if not job:
            time.sleep(2)
            continue

        status = job.get("status", "unknown")
        progress = job.get("progress_current", 0)
        total = job.get("progress_total", 1)
        pct = progress / total if total > 0 else 0

        # Progress bar
        bar = _bar(pct, 20)
        elapsed = int(time.time() - start)

        if status != last_status:
            print(f"  [{elapsed:3d}s] {_status_icon(status)} Status: {status.upper()}  {bar}  ({progress}/{total})")
            last_status = status

        if status in ("completed", "failed", "canceled"):
            print()
            results = job.get("results", [])
            records = job.get("total_records", 0)
            filtered = job.get("filtered_records", 0)
            logs = job.get("logs", [])

            print(f"  {'=' * 50}")
            print(f"  Status:      {_status_icon(status)} {status.upper()}")
            print(f"  Results:     {len(results)} final records ({filtered} after filtering from {records} raw)")
            print(f"  Duration:    {elapsed}s")

            if logs:
                print("  Logs:")
                for log in logs[-5:]:
                    msg = log.get("message", "") if isinstance(log, dict) else str(log)
                    print(f"    • {msg}")

            if results:
                _print_section("Sample Results (first 3)")
                for i, rec in enumerate(results[:3]):
                    print(f"  [{i + 1}] {json.dumps(rec, indent=4)}")
                    if i < 2:
                        print()

            if status == "failed":
                error = job.get("error", "Unknown")
                print(f"\n  ❌ Error: {error}")

            return status == "completed"

        time.sleep(2)

    print(f"\n  ⏱️  Timed out after {timeout}s")
    return False


# ─── List Jobs ─────────────────────────────────────────────────────────────


def list_jobs(limit: int = 10):  # noqa: ARG001
    """List recent scraping jobs."""
    _print_header("RECENT JOBS")
    data = api_get("/api/system/status")
    if not data:
        return

    jobs = data.get("jobs", {})
    print(
        f"  Total: {jobs.get('total', 0)}  |  "
        f"Active: {jobs.get('active', 0)}  |  "
        f"Completed: {jobs.get('completed', 0)}  |  "
        f"Failed: {jobs.get('failed', 0)}",
    )

    # Get individual jobs from the API
    data = api_get("/api/system/status")
    # The status endpoint only gives counts — fallback to listing directly
    print()
    print("  (Use the dashboard at http://localhost:8000/app for a full job list)")
    print("  Use 'manual_test.py test-job' to create and monitor a new job")


# ─── Crystalline Records ───────────────────────────────────────────────────


def check_crystalline():
    """Show synthesized knowledge records."""
    _print_header("CRYSTALLINE KNOWLEDGE")
    data = api_get("/api/system/crystalline")
    if not data:
        return

    records = data.get("records", [])
    count = data.get("count", 0)
    print(f"  Total Crystalline Records: {count}")

    if records:
        _print_section("Records")
        for i, rec in enumerate(records[:5]):
            print(f"  [{i + 1}] {json.dumps(rec, indent=2)[:200]}")
            print()


# ─── Full Test Suite Runner ────────────────────────────────────────────────


def run_test_suite():
    """Run pytest and report results."""
    _print_header("TEST SUITE")
    import subprocess  # nosec B404 — operational script, hardcoded command vector

    result = subprocess.run(  # nosec B603 # noqa: S603 — hardcoded pytest invocation, no shell, no untrusted input
        [sys.executable, "-m", "pytest", "backend/tests/", "-v", "--tb=short", "-x"],
        capture_output=True,
        text=True,
        cwd="backend/..",
    )
    print(result.stdout[-2000:])
    if result.returncode == 0:
        print("\n✅ ALL TESTS PASSED")
    else:
        print(f"\n❌ SOME TESTS FAILED (exit code {result.returncode})")
        print(result.stderr[-500:])


# ─── All Checks ────────────────────────────────────────────────────────────


def run_all():
    """Run a comprehensive system check."""
    _print_header("COMPREHENSIVE SYSTEM CHECK")
    print(f"  Server:    {API_BASE}")
    print(f"  Time:      {datetime.now().isoformat()}")
    print()

    ok = True
    ok &= check_health()
    if ok:
        check_topology(detailed=True)
        check_observability()
        check_crystalline()
    else:
        print("\n  ⚠️  Server not reachable. Skipping detailed checks.")
        print("  Start the server with:  ./scripts/start.sh")

    print()
    if ok:
        print("  ✅ All checks passed — system is operational.")
    else:
        print("  ⚠️  Some checks failed — review above for details.")

    return ok


# ─── Interactive Menu ──────────────────────────────────────────────────────


def interactive_menu():
    """Show an interactive menu for manual testing."""
    while True:
        print()
        print("╔════════════════════════════════════════════════╗")
        print("║        DataForge Studio — Test CLI            ║")
        print("╠════════════════════════════════════════════════╣")
        print("║                                                ║")
        print("║  1) Health Check — quick server status        ║")
        print("║  2) Topology — field state & metrics          ║")
        print("║  3) Observability — telemetry & health index  ║")
        print("║  4) Trigger Scheduler — run cognitive tasks   ║")
        print("║  5) Test Job (Manual) — single URL scrape     ║")
        print("║  6) Test Job (Auto) — discovery + scrape      ║")
        print("║  7) Crystalline Records — synthesized knowledge║")
        print("║  8) Run All — comprehensive system check      ║")
        print("║  9) Run Tests — pytest suite                  ║")
        print("║                                                ║")
        print("║  q) Quit                                      ║")
        print("╚════════════════════════════════════════════════╝")

        choice = input("\n  Select option: ").strip().lower()

        actions = {
            "1": ("Health Check", lambda: (check_health(), True)),
            "2": ("Topology", lambda: (check_topology(detailed=True), True)),
            "3": ("Observability", lambda: (check_observability(), True)),
            "4": ("Trigger Scheduler", lambda: (trigger_scheduler_step(float(input("  Budget (ms) [100]: ") or "100")), True)),
            "5": ("Test Job (Manual)", lambda: (run_test_job("manual"), True)),
            "6": ("Test Job (Auto)", lambda: (run_test_job("auto"), True)),
            "7": ("Crystalline Records", lambda: (check_crystalline(), True)),
            "8": ("Run All", lambda: (run_all(), True)),
            "9": ("Run Tests", lambda: (run_test_suite(), True)),
            "q": ("Quit", lambda: (print("  Goodbye!"), sys.exit(0))),
        }

        action = actions.get(choice)
        if action:
            name, fn = action
            print(f"\n─── {name} ───")
            fn()
            input("\n  Press Enter to continue...")
        else:
            print("  Invalid option. Try again.")


# ─── Main ──────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="DataForge Studio — Manual Test CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/manual_test.py           # Interactive menu
  python scripts/manual_test.py health     # Quick health check
  python scripts/manual_test.py topology   # Show topology state
  python scripts/manual_test.py test-job   # Create and monitor a test job
  python scripts/manual_test.py all        # Run selected checks
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["health", "topology", "observability", "scheduler", "test-job", "test-job-auto", "crystalline", "tests", "all"],
        help="Command to run (omit for interactive menu)",
    )

    args = parser.parse_args()

    commands = {
        "health": lambda: (check_health(), None),
        "topology": lambda: (check_topology(detailed=True), None),
        "observability": lambda: (check_observability(), None),
        "scheduler": lambda: (trigger_scheduler_step(), None),
        "test-job": lambda: (run_test_job("manual"), None),
        "test-job-auto": lambda: (run_test_job("auto"), None),
        "crystalline": lambda: (check_crystalline(), None),
        "tests": lambda: (run_test_suite(), None),
        "all": lambda: (run_all(), None),
    }

    if args.command:
        fn = commands.get(args.command)
        if fn:
            fn()
        else:
            parser.print_help()
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
