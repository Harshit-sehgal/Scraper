#!/usr/bin/env python3
"""Runtime smoke loop for DataForge API.

Runs repeated create/cancel/poll/status checks to validate orchestration behavior.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request


def _request(method: str, url: str, payload: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.getcode(), json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else "{}"
        try:
            return e.code, json.loads(body) if body else {}
        except Exception as e:
            import logging
            logging.exception(e)
            return e.code, {"detail": body}


def run_cycle(base_url: str, cycle_index: int, poll_timeout: int, expected_terminal: str) -> bool:
    payload = {
        "name": f"smoke-auto-cancel-{cycle_index}",
        "mode": "auto",
        "topic": "interior designers chennai",
        "location": "Chennai",
        "max_pages": 3,
        "max_per_domain": 2,
        "source_policy": "official_plus_directory",
        "schema_fields": [{"name": "company_name", "field_type": "string", "required": True}],
    }

    code, created = _request("POST", f"{base_url}/api/jobs", payload)
    if code != 200 or not created.get("job_id"):
        print(f"[cycle {cycle_index}] create failed: {code} {created}")
        return False

    job_id = created["job_id"]
    print(f"[cycle {cycle_index}] created job {job_id}")

    code, canceled = _request("POST", f"{base_url}/api/jobs/{job_id}/cancel")
    if code != 200:
        print(f"[cycle {cycle_index}] cancel failed: {code} {canceled}")
        return False

    print(f"[cycle {cycle_index}] cancel response: {canceled.get('message', 'ok')}")

    started = time.time()
    terminal = None
    while time.time() - started < poll_timeout:
        code, job = _request("GET", f"{base_url}/api/jobs/{job_id}", timeout=10)
        if code != 200:
            print(f"[cycle {cycle_index}] get job failed: {code} {job}")
            return False

        status = str(job.get("status") or "")
        if status in {"completed", "failed", "canceled"}:
            terminal = status
            break

        time.sleep(0.5)

    if terminal is None:
        print(f"[cycle {cycle_index}] timeout waiting for terminal status")
        return False

    if expected_terminal != "any" and terminal != expected_terminal:
        print(
            f"[cycle {cycle_index}] unexpected terminal status: "
            f"expected={expected_terminal}, got={terminal}"
        )
        return False

    code, system = _request("GET", f"{base_url}/api/system/status", timeout=10)
    if code != 200:
        print(f"[cycle {cycle_index}] system status failed: {code} {system}")
        return False

    jobs = system.get("jobs") or {}
    print(f"[cycle {cycle_index}] terminal={terminal}, system_jobs={jobs}")
    return True


def cleanup_terminal_jobs(base_url: str, keep_recent: int) -> bool:
    code, body = _request("DELETE", f"{base_url}/api/jobs/cleanup/terminal?keep_recent={max(0, keep_recent)}", timeout=20)
    if code != 200:
        print(f"[cleanup] failed: {code} {body}")
        return False

    print(f"[cleanup] {body}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DataForge runtime smoke loop")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--cycles", type=int, default=3, help="Number of cycles to run")
    parser.add_argument("--poll-timeout", type=int, default=30, help="Per-cycle terminal wait timeout in seconds")
    parser.add_argument(
        "--expected-terminal",
        choices=["canceled", "completed", "failed", "any"],
        default="canceled",
        help="Expected terminal status for each cycle",
    )
    parser.add_argument(
        "--cleanup-terminal",
        action="store_true",
        help="After cycles, call terminal cleanup endpoint",
    )
    parser.add_argument(
        "--cleanup-keep-recent",
        type=int,
        default=5,
        help="When cleanup is enabled, keep this many recent terminal jobs",
    )
    args = parser.parse_args()

    all_ok = True
    durations: list[float] = []
    success_count = 0
    for idx in range(1, max(1, args.cycles) + 1):
        t0 = time.time()
        ok = run_cycle(
            base_url=args.base_url.rstrip("/"),
            cycle_index=idx,
            poll_timeout=max(5, args.poll_timeout),
            expected_terminal=args.expected_terminal,
        )
        durations.append(time.time() - t0)
        if ok:
            success_count += 1
        all_ok = all_ok and ok

    if args.cleanup_terminal:
        all_ok = cleanup_terminal_jobs(args.base_url.rstrip("/"), args.cleanup_keep_recent) and all_ok

    if durations:
        sorted_durations = sorted(durations)
        avg = sum(sorted_durations) / len(sorted_durations)
        # Nearest-rank percentile: rank = ceil(p * n), using 1-based ranks.
        p95_rank = max(1, math.ceil(len(sorted_durations) * 0.95))
        p95 = sorted_durations[p95_rank - 1]
        print(
            "Smoke summary: "
            f"cycles={len(durations)}, success={success_count}/{len(durations)}, "
            f"avg={avg:.2f}s, p95={p95:.2f}s, max={sorted_durations[-1]:.2f}s"
        )

    if all_ok:
        print("Smoke loop PASSED")
        return 0

    print("Smoke loop FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
