"""Regression guards for the Dependabot auto-merge workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dependabot-auto-merge.yml"


def _workflow() -> dict[str, Any]:
    assert WORKFLOW.is_file(), f"missing {WORKFLOW}"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_dependabot_workflow_has_no_default_write_permissions() -> None:
    """Workflow-level token scope must be empty by default."""
    workflow = _workflow()
    assert workflow.get("permissions") == {}, (
        "dependabot-auto-merge.yml must set workflow-level permissions: {} and grant write scopes only on the patch merge job"
    )


def test_dependabot_approval_and_auto_merge_are_patch_only() -> None:
    """Minor and major dependency updates need human review."""
    jobs = _workflow()["jobs"]

    approve_if = jobs["approve-patch"]["if"]
    merge_if = jobs["enable-patch-auto-merge"]["if"]

    expected = "needs.metadata.outputs.update-type == 'version-update:semver-patch'"
    assert approve_if == expected
    assert merge_if == expected
    assert "semver-minor" not in approve_if + merge_if
    assert "semver-major" not in approve_if + merge_if


def test_dependabot_contents_write_scope_is_merge_job_only() -> None:
    """No earlier job should carry contents: write."""
    jobs = _workflow()["jobs"]

    for job_name, job in jobs.items():
        permissions = job.get("permissions", {})
        if job_name == "enable-patch-auto-merge":
            assert permissions.get("contents") == "write"
            assert permissions.get("pull-requests") == "write"
            continue
        assert permissions.get("contents") != "write", f"{job_name} exposes contents: write before merge time"
