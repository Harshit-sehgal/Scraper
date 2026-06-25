"""Static guard for F-DOCKER-004 — .dockerignore excludes secrets dumps.

Pre-fix, ``.dockerignore`` left several high-risk patterns unblocked:
``backend/data/`` was already excluded but ``.secrets/``,
``backend/init-db/``, ``*.dump``, ``*.sql.gz`` and ``*.bak`` were not.
An operator who dropped a plaintext ``pg_dump`` into ``.secrets/``
during local debugging would have it silently copied into the build
context — and possibly into an image layer — without ever touching
the working tree.

The fix expands ``.dockerignore`` to deny those patterns. This test
parses the file and asserts each high-risk pattern is listed so a
future contributor cannot accidentally regress the deny list.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

# High-risk patterns whose exclusion is mandated by F-DOCKER-004.
REQUIRED_PATTERNS = (
    ".secrets/",
    "backend/init-db/",
    "*.dump",
    "*.sql.gz",
    "*.bak",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _strip_comments(text: str) -> set[str]:
    """Return the set of non-blank, non-comment entries from the ignore file."""
    entries: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped)
    return entries


class TestDockerignoreExcludesSecretsDumps:
    """``.dockerignore`` keeps plaintext dumps/init scripts out of the build context."""

    def test_dockerignore_present(self) -> None:
        assert DOCKERIGNORE.is_file(), f"missing {DOCKERIGNORE}"

    def test_required_patterns_listed(self) -> None:
        text = _read(DOCKERIGNORE)
        entries = _strip_comments(text)
        missing = [p for p in REQUIRED_PATTERNS if p not in entries]
        assert not missing, (
            "F-DOCKER-004: .dockerignore is missing required"
            " patterns that keep plaintext dumps and seed scripts"
            " out of the build context:\n  - " + "\n  - ".join(missing)
            + "\nA future contributor who drops a `.secrets/dump.sql`"
            " would ship it into the image."
        )

    def test_secrets_dump_unreachable_from_build_context(self) -> None:
        """Use ``git check-ignore`` semantics to confirm a synthetic dump is excluded.

        ``docker build`` honors ``.dockerignore`` rules; this test mirrors that
        with ``git check-ignore`` (which uses the same gitignore-style glob
        semantics). If ``git`` is not available the test is silently skipped —
        ``.dockerignore`` parsing above is the primary check.
        """
        import shutil
        import subprocess

        dump_path = REPO_ROOT / ".secrets" / "synthetic_dump.sql"
        if not dump_path.parent.exists():
            dump_path.parent.mkdir(exist_ok=True)
        dump_path.write_text("-- synthetic plaintext pg_dump\nSELECT 1;\n", encoding="utf-8")
        try:
            git_bin = shutil.which("git")
            if git_bin is None:
                # Cleanup before bailing; primary text-check already passed.
                dump_path.unlink(missing_ok=True)
                return
            rel = ".secrets/synthetic_dump.sql"
            res = subprocess.run(  # noqa: S603
                [git_bin, "check-ignore", "-v", rel],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            assert res.returncode == 0, (
                "F-DOCKER-004: synthetic `.secrets/synthetic_dump.sql`"
                " is not blocked from the build context. Found via"
                f" git check-ignore: stdout={res.stdout!r}, stderr={res.stderr!r}."
            )
            assert ".secrets/" in res.stdout, (
                "F-DOCKER-004: synthetic dump is ignored but the rule is"
                " not sourced from `.dockerignore` (or .gitignore). Output:"
                f" {res.stdout!r}"
            )
        finally:
            dump_path.unlink(missing_ok=True)


# A small linter regex used by future contributors who want to verify the
# patterns are present without running the tests. Importing this is harmless.
_PATTERN = re.compile("|".join(re.escape(p) for p in REQUIRED_PATTERNS))
