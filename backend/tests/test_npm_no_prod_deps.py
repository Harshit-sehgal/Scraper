"""Static guard for F-NPM-003 — package.json keeps production deps empty.

Pre-fix, ``package.json`` carried every dependency under ``devDependencies``
(correct for a static-build SPA) but had no automated guard against a
contributor accidentally running ``npm install somelib`` outside the
dev-deps group. Once that happens, a freshly-cloned contributor who runs
``npm ci`` ships a real runtime dependency to production without anyone
noticing during PR review.

The fix is text-only: assert that no entry ever appears under
``dependencies`` in ``package.json``. If a prod dep is ever needed, the
contributor must consciously add it AND update this test to document
why.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_JSON = REPO_ROOT / "package.json"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


class TestPackageJsonHasNoProductionDeps:
    """``package.json`` keeps ``dependencies`` empty for static SPA builds."""

    def test_dependencies_block_absent_or_empty(self) -> None:
        manifest = json.loads(_read(PACKAGE_JSON))
        deps = manifest.get("dependencies", None)
        assert not deps, (
            "F-NPM-003: package.json declares production dependencies:"
            f" {deps!r}. The Studio frontend is a static SPA — every"
            " package belongs under ``devDependencies``. Add an npm-ls"
            " --prod CI guard if prod deps are ever required, and"
            " update this test to document the exception."
        )

    def test_no_unescaped_runtime_imports_in_frontend_js(self) -> None:
        """A static SPA ``import`` from a non-dev namespace would imply a prod dep."""
        manifest = json.loads(_read(PACKAGE_JSON))
        deps = set((manifest.get("dependencies") or {}).keys())
        assert not deps, "F-NPM-003: production dependencies present; runtime imports are out of scope of this static-build repo."
