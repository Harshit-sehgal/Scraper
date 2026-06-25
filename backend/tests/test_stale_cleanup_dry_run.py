"""Static guard for F-CI-009 — stale-cleanup dry-run input.

Regression target:
    - F-CI-009 (P2): ``.github/workflows/stale-cleanup.yml`` runs on a
      daily cron and auto-closes branches/PRs. A mislabeled hot-fix
      release PR could be auto-closed because the operator has no way
      to preview which items will be touched.

Lock-in: the workflow must declare a manual ``workflow_dispatch`` input
named ``dry-run`` that wires through to ``actions/stale.dry-run:`` so
the operator can dry-run the cleanup without labelling or closing.

The test is text-only and lives next to the workflow file to keep the
yaml lint portable.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "stale-cleanup.yml"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _workflow_data(text: str) -> dict:
    return yaml.safe_load(text)


class TestStaleCleanupDryRunGate:
    """The stale-cleanup workflow exposes a dry-run input and wires it through."""

    def test_workflow_file_exists(self) -> None:
        assert WORKFLOW.is_file(), f"missing stale-cleanup workflow at {WORKFLOW}"

    def test_workflow_dispatch_accepts_dry_run_input(self) -> None:
        """``workflow_dispatch`` must declare a ``dry-run`` boolean input."""
        text = _read(WORKFLOW)
        assert "workflow_dispatch:" in text, (
            f"{WORKFLOW}: missing `workflow_dispatch:` trigger — an operator"
            " can no longer run the cleanup on demand"
            " (F-CI-009: a mislabeled hot-fix PR needs to be inspected before close)."
        )
        # The input must be named `dry-run` and typed boolean; default false.
        data = _workflow_data(text)
        on = data.get(True) or data.get("on") or {}
        dispatch = on.get("workflow_dispatch")
        assert isinstance(dispatch, dict), (
            f"{WORKFLOW}: `workflow_dispatch:` must be a mapping with `inputs:`"
            " — F-CI-009 requires a structured input for dry-run."
        )
        inputs = dispatch.get("inputs") or {}
        assert "dry-run" in inputs, (
            f"{WORKFLOW}: `workflow_dispatch.inputs` must declare `dry-run`"
            " so an operator can preview what will be closed (F-CI-009)."
        )
        dry_run = inputs["dry-run"]
        assert dry_run.get("type") == "boolean", f"{WORKFLOW}: `dry-run` input must be type=boolean"
        assert dry_run.get("default") is False, (
            f"{WORKFLOW}: `dry-run` must default to false so the schedule"
            " still closes stale PRs by default (F-CI-009: preview-only by opt-in)."
        )

    def test_dry_run_wired_through_to_action(self) -> None:
        """``actions/stale`` must consume the input via ``dry-run:``."""
        text = _read(WORKFLOW)
        assert "dry-run:" in text, (
            f"{WORKFLOW}: `actions/stale` step must pass a `dry-run:` arg."
            " Without it the input is cosmetic — pull requests will still close."
        )
        assert "${{ inputs.dry-run" in text, (
            f"{WORKFLOW}: `dry-run:` must reference ${{ inputs.dry-run }}"
            " so the operator-toggle actually reaches the action."
            " F-CI-009: a hard-coded false is no safer than no input."
        )

    def test_exempt_labels_pinned_in_workflow(self) -> None:
        """Belt and suspenders: hot-fix release labels must remain exempt.

        F-CI-009 is about the dry-run affordance, not removing the
        exempt list. We sanity-check that the existing exempt labels
        are still present so future contributors don't accidentally
        drop ``security``/``keep-open`` while touching the input block.
        """
        text = _read(WORKFLOW)
        for label in ("keep-open", "dependencies", "security"):
            assert label in text, (
                f"{WORKFLOW}: `{label}` exempt label was removed."
                " F-CI-009 is about adding dry-run, not weakening the exempt list."
            )
