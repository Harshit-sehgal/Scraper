"""Verify every third-party ``uses:`` line in CI workflows is SHA-pinned.

F-CI-003 asks for defense-in-depth against mutable-tag supply-chain
compromise: every ``uses: <repo>@<ref>`` reference in
``.github/workflows/*.yml`` must point at a 40-character commit SHA
rather than a SemVer tag. Mutable tags (e.g. ``@v4``) let a
maintainer push a swap and have CI run the new code on the next
push; the SHA is the only line of defense.

We intentionally allow:

- ``uses: ./local-path`` - a relative workflow reference, not a
  third-party action
- ``uses: <repo>@<sha>`` where ``<sha>`` is a 40-lowercase-hex string
- Inline ``# <tag>`` comments after the pin (used to keep a
  human-readable trace of the version)
- ``appleboy/telegram-action@<sha>`` with the original master pin
  style plus a ``# master @ <date>`` annotation

Called from ``.github/workflows/ci.yml::fast-gates`` and from the
local repo-bound regression test ``backend/tests/test_workflow_action_pins.py``.

Exit code 0 = all pins are SHA, 1 = at least one mutable ref remains,
with a per-line report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _iter_workflows(directory: Path) -> list[Path]:
    return sorted(p for pattern in ("*.yml", "*.yaml") for p in directory.glob(pattern) if p.is_file())


def check_directory(workflows_dir: Path) -> tuple[int, list[str]]:
    """Walk the workflows directory and return (exit_code, problems).

    A non-zero exit code means there is at least one mutable ref.
    Each ``problems`` entry is a human-readable ``<file>:<line>`` line.
    """
    problems: list[str] = []
    for wf in _iter_workflows(workflows_dir):
        for lineno, raw in enumerate(wf.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = raw.lstrip()
            if not stripped.startswith("- uses:") and not stripped.startswith("uses:"):
                continue
            # Pull the trimmed section after ``uses:`` and strip any
            # trailing ``# ...`` comment so we only see the spec.
            after = raw.split("uses:", 1)[1]
            after = re.split(r"\s#", after, maxsplit=1)[0].strip().strip("\"'")
            if not after:
                problems.append(f"{wf.name}:{lineno}: missing @<ref> in uses: ''")
                continue
            action, _, ref = after.partition("@")
            if action.startswith(("./", "/")):
                # Local action reference; safe by definition.
                continue
            if not ref:
                problems.append(f"{wf.name}:{lineno}: missing @<ref> in uses: {action!r}")
                continue
            if SHA_RE.fullmatch(ref):
                # SHA-pinned: the desired form.
                continue
            problems.append(f"{wf.name}:{lineno}: mutable ref {action!r}@{ref!r} (must be a 40-char SHA)")
    return (1 if problems else 0), problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <workflows-dir>", file=sys.stderr)
        return 2
    workflows_dir = Path(argv[1])
    if not workflows_dir.is_dir():
        print(f"error: not a directory: {workflows_dir}", file=sys.stderr)
        return 2
    exit_code, problems = check_directory(workflows_dir)
    if problems:
        print("Mutable `uses:` references found (F-CI-003):", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
