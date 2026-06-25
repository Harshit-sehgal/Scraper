"""Regression test for F-CI-004 auto-fix fork filtering.

The bug: ``.github/workflows/auto-fix.yml`` triggers on
``issue_comment: created`` and ``pull_request: labeled``, writes with a
PAT, and does not gate the job on
``github.event.pull_request.head.repo.full_name == github.repository``.
That means anyone who opens a PR from a fork and comments ``/format``
(or applies the ``auto-format`` label) can push to the PR branch and run
``ruff format`` / ``prettier --write`` over arbitrary paths.

The label path can reject forks at job-dispatch time via
``head.repo.full_name == github.repository``. The comment path has to
fetch the PR head repo first, so write-capable steps must be guarded by
``steps.pr.outputs.allowed == 'true'``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_FIX = REPO_ROOT / ".github" / "workflows" / "auto-fix.yml"


def _workflow() -> dict:
    return yaml.safe_load(AUTO_FIX.read_text(encoding="utf-8"))


def _job_if_expression() -> str:
    """Return the raw ``if:`` expression of the ``format-fix`` job."""
    job = _workflow()["jobs"]["format-fix"]
    expr = job.get("if")
    assert isinstance(expr, str), f"format-fix job must declare an `if:` expression (F-CI-004), got {expr!r}"
    return expr


def test_auto_fix_workflow_exists() -> None:
    assert AUTO_FIX.is_file(), f"missing auto-fix workflow at {AUTO_FIX}"


def test_format_fix_job_has_fork_filter() -> None:
    """The pull_request label path must not run for fork PRs."""
    expr = _job_if_expression()
    assert "github.event.pull_request.head.repo.full_name" in expr, (
        f"format-fix job must reference github.event.pull_request.head.repo.full_name to filter forks (F-CI-004). Got: {expr!r}"
    )
    assert "github.repository" in expr, f"format-fix job must compare against github.repository (F-CI-004). Got: {expr!r}"


def test_format_fix_job_rejects_fork_pr() -> None:
    """The job's pull_request branch must compare head repo by equality."""
    expr = _job_if_expression()
    # Strict equality is the documented safe pattern.
    assert "==" in expr, (
        f"format-fix `if:` must use strict equality `==` not `!=` to be the documented safe pattern (F-CI-004). Got: {expr!r}"
    )
    assert "!=" not in expr, f"format-fix `if:` must not use inequality `!=` (F-CI-004). Got: {expr!r}"


def test_no_contents_write_for_fork_pivot() -> None:
    """Workflow-level token permissions must not expose contents: write."""
    permissions = _workflow().get("permissions", {})
    assert permissions.get("contents") != "write"


def test_auto_fix_uses_dedicated_write_token_only() -> None:
    """Auto-fix pushes must not fall back to the workflow GITHUB_TOKEN."""
    env = _workflow().get("env", {})
    token_expr = env.get("GH_TOKEN", "")
    assert "FORMAT_FIX_BOT_TOKEN" in token_expr
    assert "GITHUB_TOKEN" not in token_expr


def test_write_capable_steps_require_same_repo_pr() -> None:
    """Formatting and push steps must be skipped for fork PR branches."""
    steps = _workflow()["jobs"]["format-fix"]["steps"]
    guarded_step_names = {
        "Set up Python ${{ env.PYTHON_VERSION }}",
        "Install Python deps",
        "Set up Node",
        "Install Node deps",
        "Fix Ruff formatting",
        "Fix Prettier formatting",
        "Commit and push fixes",
    }

    checkout_steps = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkout_steps) == 1
    assert checkout_steps[0].get("if") == "steps.pr.outputs.allowed == 'true'"

    require_token_step = next(step for step in steps if step.get("name") == "Require format-fix token")
    assert require_token_step.get("if") == "steps.pr.outputs.allowed == 'true'"
    assert "FORMAT_FIX_BOT_TOKEN is required" in require_token_step["run"]

    for step in steps:
        if step.get("name") in guarded_step_names:
            assert step.get("if") == "steps.pr.outputs.allowed == 'true'", step


def test_comment_path_sets_allowed_output_from_head_repo() -> None:
    """The /format path must fetch the PR head repo before checkout."""
    steps = _workflow()["jobs"]["format-fix"]["steps"]
    get_pr_step = next(step for step in steps if step.get("name") == "Get PR branch ref")
    run_script = get_pr_step["run"]
    expr = _job_if_expression()
    assert "github.event.issue.pull_request" in expr
    assert "HEAD_REPO" in run_script
    assert "allowed=true" in run_script
    assert "allowed=false" in run_script
