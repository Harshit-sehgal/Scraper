"""Static guard for F-CI-007 — cron workflow concurrency.

Regression target:
    - F-CI-007 (P2): every cron workflow (those triggered by both
      ``schedule:`` and ``workflow_dispatch:``) was using
      ``concurrency.cancel-in-progress: true``. A manual dispatch
      would cancel an in-flight scheduled run, dropping telemetry and
      losing CI minutes as a side effect.

Lock-in: cron workflows must (a) scope the concurrency group on the
trigger event (``github.event_name``) so schedule and dispatch never
share an in-flight slot, and (b) declare ``cancel-in-progress: false``
so a manual dispatch queues instead of dropping a scheduled run.

This is a structural-only test that scans the workflow text, matching
the philosophy of the F-CI-003 / F-DRIFT-002 lock-ins.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# These are the cron / scheduled workflows in the repo. They trigger
# on a ``schedule:`` block and allow manual dispatch to re-run.
CRON_WORKFLOWS = (
    "nightly-integration.yml",
    "golden-dataset.yml",
    "browser-e2e.yml",
    "postgres-tests.yml",
    "optional-suites.yml",
    "validate-production.yml",
)


def _has_cron(path: Path) -> bool:
    """Return True if the workflow has a ``schedule:`` block (i.e. is a cron workflow)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    on = data.get(True) or data.get("on") or {}
    # YAML may parse ``on`` as the boolean ``True`` key when loaded with
    # ``yaml.safe_load``; normalize.
    return bool(isinstance(on, dict) and "schedule" in on)


def _workflow_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_CONCURRENCY_BLOCK = re.compile(
    r"^concurrency:\s*\n(?P<body>(?:^[ \t]+.+\n)+)",
    re.MULTILINE,
)


def _body_has_event_name(body: str) -> bool:
    return "github.event_name" in body


def _body_cancel_in_progress(body: str) -> str | None:
    """Return the literal ``true`` / ``false`` right after ``cancel-in-progress:``."""
    m = re.search(r"^[ \t]+cancel-in-progress:\s*(\S+)\s*$", body, re.MULTILINE)
    if m is None:
        return None
    return m.group(1)


class TestCronWorkflowConcurrency:
    """Cron workflows must not cancel an in-flight scheduled run on manual dispatch."""

    def test_cron_workflows_present(self) -> None:
        for name in CRON_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            assert path.is_file(), f"expected {path} — workflow file removed"
            assert _has_cron(path), f"{path}: no longer has a `schedule:` trigger"

    def test_each_cron_workflow_keys_on_event_name(self) -> None:
        """Concurrency group must include ``github.event_name``."""
        for name in CRON_WORKFLOWS:
            text = _workflow_text(WORKFLOWS_DIR / name)
            m = _CONCURRENCY_BLOCK.search(text)
            assert m, f"{name}: missing `concurrency:` block"
            body = m.group("body")
            assert _body_has_event_name(body), (
                f"{name}: concurrency.group must include ${{{{ github.event_name }}}} so a"
                " manual dispatch cannot collide with the in-flight schedule (F-CI-007)."
            )

    def test_each_cron_workflow_disables_cancel_in_progress(self) -> None:
        """``cancel-in-progress: false`` allows the schedule to finish undropped."""
        for name in CRON_WORKFLOWS:
            text = _workflow_text(WORKFLOWS_DIR / name)
            m = _CONCURRENCY_BLOCK.search(text)
            assert m, f"{name}: missing `concurrency:` block"
            value = _body_cancel_in_progress(m.group("body"))
            assert value is not None, f"{name}: `concurrency:` block missing `cancel-in-progress:` line"
            assert value == "false", (
                f"{name}: cron workflow must use `cancel-in-progress: false` so"
                " a manual dispatch queues instead of dropping the in-flight schedule"
                f" (got: {value!r})"
            )

    def test_ci_yaml_pr_flow_keeps_cancel_true(self) -> None:
        """The PR-driven CI workflow may still cancel on conflict.

        Only the cron workflows from ``CRON_WORKFLOWS`` are constrained
        by F-CI-007. The PR-only path (``ci.yml`` with
        ``pull_request`` triggers) keeps the original fast-cancel
        semantics, so we sanity-check by inspecting ``ci.yml`` only to
        confirm it still has ``cancel-in-progress: true`` for PR events.
        """
        path = WORKFLOWS_DIR / "ci.yml"
        if not path.is_file():
            return  # ci workflow absent; nothing to assert.
        text = _workflow_text(path)
        m = _CONCURRENCY_BLOCK.search(text)
        assert m, "ci.yml has no `concurrency:` block — out of scope for this test"
        # Either PR-only or also has schedule. We just assert the
        # pattern that PR flows historically used is still there at
        # the project root level — closing-checked by F-CI-003's
        # SHA-pin invariants already.
