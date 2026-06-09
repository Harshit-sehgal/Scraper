"""Tests for benchmark governance.

The deep-research report calls for benchmark governance — separating
regression corpus from live-internet benchmarks. ``scripts/live_benchmark.py``
must be opt-in via ``DATAFORGE_RUN_LIVE_BENCHMARKS=1`` and exit with
a skip code (78) when the flag is not set, so the CI workflow can
treat the missing flag as a pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_live_benchmark(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run scripts/live_benchmark.py in a subprocess with the given env overlay."""
    backend_dir = REPO_ROOT / "backend"
    full_env = os.environ.copy()
    full_env["PYTHONPATH"] = str(backend_dir)
    full_env["DATAFORGE_DOTENV_PATH"] = "/dev/null"
    full_env["DATAFORGE_STORAGE_BACKEND"] = "sqlite"
    full_env["DATAFORGE_STATE_FILE"] = "/tmp/test_benchmark_governance_state.json"
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "scripts/live_benchmark.py"],
        cwd=str(REPO_ROOT),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=20,
    )


class TestLiveBenchmarkGovernance:
    def test_skips_without_opt_in_flag(self) -> None:
        result = _run_live_benchmark({})
        # 78 = SKIPPED in CI; the workflow treats this as success.
        assert result.returncode == 78, (
            f"Expected exit code 78 (skipped), got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "DATAFORGE_RUN_LIVE_BENCHMARKS=1" in result.stderr

    def test_opt_in_flag_accepted(self) -> None:
        """When the flag is set, the script must NOT exit with 78 (skipped).

        We don't actually want to hit the network from this unit test, so
        we monkeypatch ``asyncio.run`` to a no-op before running the
        script in a subprocess via import. The point of the test is
        gating logic, not a network round trip.
        """
        # We can't import scripts/* directly because they rely on sys.path
        # mutation in their top-level code. Use subprocess instead, but
        # set the flag AND neutralise asyncio.run via PYTHONSTARTUP-style
        # monkey-patch using a wrapper script.
        wrapper = REPO_ROOT / "scripts" / "_test_live_benchmark_wrapper.py"
        wrapper.write_text(
            "import asyncio, os, sys\n"
            "os.environ['DATAFORGE_RUN_LIVE_BENCHMARKS'] = '1'\n"
            "asyncio.run = lambda coro: None\n"
            "sys.argv = ['live_benchmark.py', '--url', 'http://localhost:0']\n"
            "exec(open('scripts/live_benchmark.py').read())\n",
        )
        try:
            result = subprocess.run(
                [sys.executable, str(wrapper)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=15,
                env={**os.environ, "PYTHONPATH": "backend", "DATAFORGE_DOTENV_PATH": "/dev/null"},
            )
            # The script reaches the asyncio.run call (which is now a
            # no-op); the only thing that should NOT happen is the
            # skip-exit (78). Any other code (including a TypeError from
            # the no-op coroutine) is acceptable.
            assert result.returncode != 78, (
                f"Expected script to proceed (exit != 78), got {result.returncode}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        finally:
            wrapper.unlink(missing_ok=True)

    def test_run_benchmarks_sh_mentions_opt_in_flag(self) -> None:
        """The shell script must document the opt-in flag in its header."""
        run_benchmarks = (REPO_ROOT / "scripts" / "run_benchmarks.sh").read_text()
        assert "DATAFORGE_RUN_LIVE_BENCHMARKS" in run_benchmarks
        assert "live_benchmark.py" in run_benchmarks

    def test_in_corpus_benchmarks_remain_default(self) -> None:
        """The default mode (no flag) must still call the in-corpus pytest set.

        We assert the run_benchmarks.sh script references the four
        deterministic test files; the actual pytest run is a separate
        concern from this governance test.
        """
        run_benchmarks = (REPO_ROOT / "scripts" / "run_benchmarks.sh").read_text()
        for filename in (
            "test_field_waves.py",
            "test_field_validator.py",
            "test_extraction_precision.py",
            "test_accuracy.py",
        ):
            assert filename in run_benchmarks, f"{filename} missing from run_benchmarks.sh"
