"""Regression test for F-CI-003 action pinning.

The actual guard lives at ``scripts/check_workflow_action_pins.py`` and is
called from CI. This test invokes the same function against the real
workflows tree to make sure local runs see the failure before pushing.

F-CI-003 rationale: a mutable tag like ``@v4`` lets an upstream action
maintainer push a tag to swap the contents CI runs; only a 40-char commit
SHA is immutable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_workflow_action_pins.py"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"


def _run_checker() -> subprocess.CompletedProcess[str]:
    """Invoke the checker as a subprocess so we exercise its real CLI entry."""
    return subprocess.run(
        [sys.executable, str(CHECKER), str(WORKFLOWS_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )


def _dependabot_config() -> dict[str, Any]:
    assert DEPENDABOT_CONFIG.is_file(), f"missing {DEPENDABOT_CONFIG}"
    return yaml.safe_load(DEPENDABOT_CONFIG.read_text(encoding="utf-8"))


def test_checker_script_exists() -> None:
    assert CHECKER.is_file(), f"missing checker script at {CHECKER}"


def test_workflows_dir_present() -> None:
    assert WORKFLOWS_DIR.is_dir(), f"missing workflows dir at {WORKFLOWS_DIR}"


def test_checker_reports_no_mutable_refs() -> None:
    """All third-party uses: must be SHA-pinned (F-CI-003)."""
    proc = _run_checker()
    assert proc.returncode == 0, (
        f"check_workflow_action_pins.py reported mutable refs:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_checker_flags_a_synthetic_mutable_ref() -> None:
    """Self-test: write a temp workflow with @v4 and confirm the guard catches it.

    Uses a private tempdir with a synthetic copy of the workflows layout
    so we don't pollute the real tree or race with other tests.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bad_wf = tmp_path / "synthetic.yml"
        bad_wf.write_text(
            "name: synthetic\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(CHECKER), str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, (
            f"checker should exit 1 on mutable ref, got 0.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "actions/checkout" in proc.stderr
        assert "v4" in proc.stderr


def test_checker_allows_sha_pins_with_tag_comment() -> None:
    """A leading SHA followed by a `# v4` annotation is the desired form."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        good_wf = tmp_path / "pinned.yml"
        good_wf.write_text(
            "name: pinned\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(CHECKER), str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, (
            f"checker should accept SHA-pinned ref with tag comment.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def test_checker_allows_local_actions() -> None:
    """Local ``./relative`` action references are not third-party."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        local_wf = tmp_path / "local.yml"
        local_wf.write_text(
            "name: local\n"
            "on: [push]\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: ./scripts/local-action\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(CHECKER), str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, (
            f"checker should allow local action references.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def test_dependabot_refreshes_github_actions_pins() -> None:
    """Dependabot must track action updates so SHA pins stay maintainable."""
    updates = _dependabot_config().get("updates", [])
    github_actions_updates = [
        entry for entry in updates if entry.get("package-ecosystem") == "github-actions" and entry.get("directory") == "/"
    ]

    assert github_actions_updates, "dependabot.yml must include a github-actions update entry for /"
    entry = github_actions_updates[0]
    assert entry.get("schedule", {}).get("interval") == "weekly"
    assert entry.get("groups", {}).get("github-actions-pins", {}).get("patterns") == ["*"]
