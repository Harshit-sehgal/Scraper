"""Static guard for F-NPM-001 — package.json pins are caret-free & lockfile-matched.

Pre-fix, all dev-dependencies in ``package.json`` used ``^`` ranges. While
CI always uses ``npm ci`` (lockfile-pinned), an ``npm install`` outside CI
would happily drift within the ``^`` range — and a stray
``npm update <pkg>`` could jump a dev tool to a fresh major in CI prior
to ``package-lock.json`` being re-checked-in.

The fix pins each dev-dependency to the exact version resolved in the
lockfile. This test then locks in two invariants:

1. ``package.json`` contains no caret (``^``), tilde (``~``), or other
   range operators on any dependency version.
2. Every dependency listed in ``package.json`` (dev or prod) matches the
   ``version`` field for the same key inside ``package-lock.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_JSON = REPO_ROOT / "package.json"
LOCKFILE = REPO_ROOT / "package-lock.json"

# Range operators that allow drift: ``^``, ``~``, ``>=``, ``<=``, ``>``,
# ``<``, ``*``, ``x``. We strip values that match exact pins like
# ``1.2.3`` or ``1.2.3-beta.1``.
_RANGE_TOKEN = re.compile(r"[\^~]|>=|<=|[<>]\s*|\*|[xX]\s*\.\s*[xX]")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


class TestPackageJsonPinnedToLockfile:
    """``package.json`` pins match lockfile — no range drift."""

    def test_package_and_lock_present(self) -> None:
        assert PACKAGE_JSON.is_file(), f"missing {PACKAGE_JSON}"
        assert LOCKFILE.is_file(), f"missing {LOCKFILE}"

    def test_no_caret_or_tilde_in_dependencies(self) -> None:
        """No ``^``/``~`` etc. range in ``dependencies`` or ``devDependencies``."""
        manifest = json.loads(_read(PACKAGE_JSON))
        deps = manifest.get("dependencies", {}) or {}
        devdeps = manifest.get("devDependencies", {}) or {}
        # Also catch peer/optional if present.
        peers = manifest.get("peerDependencies", {}) or {}
        optional = manifest.get("optionalDependencies", {}) or {}

        bad: list[str] = []
        for group_name, group in (
            ("dependencies", deps),
            ("devDependencies", devdeps),
            ("peerDependencies", peers),
            ("optionalDependencies", optional),
        ):
            for name, spec in group.items():
                if _RANGE_TOKEN.search(spec):
                    bad.append(f"{group_name}.{name} = {spec!r}")

        assert not bad, (
            "F-NPM-001: package.json contains range-pinned dependencies."
            " Pinning everything to exact versions matches the lockfile"
            " and stops `npm install` (vs `npm ci`) from drifting:\n  - "
            + "\n  - ".join(bad)
        )

    def test_pinned_versions_match_lockfile(self) -> None:
        """Each pinned version must agree with the lockfile's resolved version."""
        manifest = json.loads(_read(PACKAGE_JSON))
        lock = json.loads(_read(LOCKFILE))

        lock_pkgs = lock.get("packages", {})
        # If lockfile v2 describes root dependencies separately, prefer
        # that; but most npm 7+ writes each dep into ``packages``.
        mismatches: list[str] = []

        for group_name in ("dependencies", "devDependencies", "peerDependencies"):
            group = manifest.get(group_name, {}) or {}
            for name, spec in group.items():
                # Ignore non-version specs that wouldn't be in packages/.
                key = f"node_modules/{name}"
                lock_entry = lock_pkgs.get(key)
                if lock_entry is None:
                    if spec.startswith("file:") or spec.startswith("link:"):
                        continue
                    mismatches.append(f"{group_name}.{name}={spec!r}: not found in lockfile")
                    continue
                resolved = lock_entry.get("version")
                if resolved != spec:
                    mismatches.append(
                        f"{group_name}.{name}: package.json says {spec!r},"
                        f" lockfile says {resolved!r}"
                    )

        assert not mismatches, (
            "F-NPM-001: package.json pins disagree with package-lock.json:\n  - "
            + "\n  - ".join(mismatches)
            + "\nRun `npm install` (not `npm ci`) to regenerate, or edit"
            " package.json to match the lockfile's resolved version."
        )
