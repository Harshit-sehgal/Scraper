"""Static guard for F-NPM-002 — npm lockfile signature integrity.

Pre-fix, CI ran ``npm ci`` only — the lockfile was loaded from cache
and tests ran against it without verifying each package's signature
against the registry. A malicious dependency bump (or a tampered
lockfile) would surface only when a downstream bug made it visible.

The fix adds ``npm audit signatures`` after ``npm ci`` so the workflow
fails closed whenever a package's signature can no longer be
verified. This is text-only; ``npm audit signatures`` itself requires
network access at runtime and depends on the registry publishing
public keys, but the workflow logic is verifiable from source.

Lock-in: every workflow that runs ``npm ci`` MUST include a
follow-up ``npm audit signatures`` step.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

WORKFLOWS_WITH_NPM = (
    "ci.yml",
    "validate-production.yml",
    "browser-e2e.yml",
    "auto-fix.yml",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


_AUDIT_SIG = re.compile(r"npm\s+audit\s+signatures")
_NPM_CI = re.compile(r"\bnpm\s+ci\b")


class TestNpmLockfileSignatureGuard:
    """Workflows that run ``npm ci`` MUST also ``npm audit signatures``."""

    def test_workflows_exist(self) -> None:
        for name in WORKFLOWS_WITH_NPM:
            path = WORKFLOWS_DIR / name
            assert path.is_file(), f"expected {path} — workflow file removed"

    def test_each_workflow_verifies_signatures(self) -> None:
        """Every npm-installing workflow must check package signatures."""
        for name in WORKFLOWS_WITH_NPM:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            if not _NPM_CI.search(text):
                continue  # Workflow without npm ci; nothing to assert.
            assert _AUDIT_SIG.search(text), (
                f"{name}: workflow runs ``npm ci`` but is missing"
                " ``npm audit signatures``. F-NPM-002: a tampered"
                " lockfile or untrusted package signature will slip"
                " through because no integrity verification step"
                " exists. Add ``npm audit signatures`` immediately"
                " after ``npm ci``."
            )

    def test_signatures_step_runs_after_install(self) -> None:
        """``npm audit signatures`` must come after ``npm ci``."""
        for name in WORKFLOWS_WITH_NPM:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            ci_match = _NPM_CI.search(text)
            aud_match = _AUDIT_SIG.search(text)
            if ci_match is None or aud_match is None:
                continue
            assert aud_match.start() > ci_match.start(), (
                f"{name}: ``npm audit signatures`` must follow"
                " ``npm ci`` so the cache populates first. The audit"
                " step is currently before the install — F-NPM-002"
                " regression."
            )
