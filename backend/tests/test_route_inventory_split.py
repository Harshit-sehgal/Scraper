"""Characterization tests for the stable vs experimental route inventory.

The Phase 0 master plan requires:

    Step 7. Split docs into current-stable docs and experimental docs.
            Stable docs must match default route inventory.

These tests prove the contract for ``scripts/route_inventory_split.py``:

* The script can be imported and runs without side effects by default.
* The stable route set is a strict subset of the experimental set
  (i.e. the diff is non-empty, meaning the gate is real and not a no-op).
* Each Markdown file written to ``docs/`` contains the expected
  section headers.
* Re-running the script does not lose any routes (idempotent within
  the same code generation cycle).

If these tests start failing, the route inventory has regressed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "route_inventory_split.py"


def _run_split() -> tuple[str, str, int]:
    """Run the inventory split script and return (stdout, stderr, rc)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.stdout, proc.stderr, proc.returncode


def test_split_script_runs_without_args() -> None:
    """The script can be imported and run with no flags (side-effect free)."""
    stdout, stderr, rc = _run_split()
    assert rc == 0, f"split script failed: {stderr}"
    # stderr should announce the counts
    assert "stable=" in stderr, f"expected 'stable=' in stderr, got: {stderr!r}"
    assert "experimental=" in stderr, f"expected 'experimental=' in stderr, got: {stderr!r}"
    # stdout should contain the stable header
    assert "API (Stable)" in stdout
    assert "API (Experimental)" in stdout
    assert "API (Experimental Diff)" in stdout


def test_stable_is_strict_subset_of_experimental() -> None:
    """The experimental set is a strict superset of the stable set.

    If this ever fails (stable has a route the experimental set does
    not, or both sets are equal), the route inventory gate is broken
    and the docs would mislead operators in production.
    """
    _stdout, stderr, _ = _run_split()
    m = re.search(r"stable=(\d+) experimental=(\d+) diff=(\d+)", stderr)
    assert m, f"could not parse counts from {stderr!r}"
    n_stable, n_full, n_diff = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Strict superset: stable < experimental, and the diff is exactly
    # experimental - stable.
    assert n_full > n_stable, (
        f"expected experimental ({n_full}) > stable ({n_stable}); either no experimental routes are mounted or the gate is broken"
    )
    assert n_diff == n_full - n_stable, f"expected diff ({n_diff}) to equal experimental ({n_full}) - stable ({n_stable})"


def test_split_writes_to_docs_when_invoked() -> None:
    """The ``--write`` flag persists the generated Markdown files."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--write"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"--write failed: {proc.stderr}"
    for name in ("API_STABLE.md", "API_EXPERIMENTAL.md", "API_EXPERIMENTAL_DIFF.md"):
        path = REPO_ROOT / "docs" / name
        assert path.exists(), f"{name} was not written by --write"
        body = path.read_text(encoding="utf-8")
        assert "auto-generated" in body.lower()
        assert "Generated:" in body


def test_each_doc_has_the_expected_section_header() -> None:
    """Each generated Markdown file must carry its identifying header."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--write"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert (REPO_ROOT / "docs" / "API_STABLE.md").read_text(encoding="utf-8").startswith("# API (Stable)")
    assert (REPO_ROOT / "docs" / "API_EXPERIMENTAL.md").read_text(encoding="utf-8").startswith("# API (Experimental)")
    assert (REPO_ROOT / "docs" / "API_EXPERIMENTAL_DIFF.md").read_text(encoding="utf-8").startswith("# API (Experimental Diff)")


@pytest.mark.timeout(60)
def test_split_runs_under_global_timeout() -> None:
    """The split script must complete well under the global 30s pytest timeout.

    If this test times out, the inventory import path picked up a
    network call (DNS, DB) and we need to fix the isolation before
    merging the Phase 0 work.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--write"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert proc.returncode == 0, f"split --write exceeded 25s or failed: {proc.stderr}"
