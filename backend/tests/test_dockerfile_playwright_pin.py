"""Static guard for F-DOCKER-003 — Dockerfile pins Playwright Chromium version.

Pre-fix, every ``docker build`` ran ``playwright install chromium``
without a version pin. The browser release followed whatever shipped in
``pyproject.toml``'s ``playwright>=1.45.0,<2.0.0`` constraint, so two
builds run back-to-back could install different Chromium tarballs. That
breaks reproducible builds AND lets a hostile Playwright release slide
uncontrolled Chromium into a freshly-built image.

The fix adds a ``PLAYWRIGHT_BROWSERS_VERSION=0`` ``ARG`` (env-exported
so runtime can see it too). When built with
``--build-arg PLAYWRIGHT_BROWSERS_VERSION=<revision>`` the explicit
revision is forwarded to ``playwright install``, locking the tarball.
``=0`` (default) keeps the legacy "follow Playwright's release" path so
unmarked rebuilds don't break.

This test statically asserts:

1. The ``ARG PLAYWRIGHT_BROWSERS_VERSION=...`` declaration exists.
2. Both the ``dev`` and ``production`` stages branch on the env var so
   the pin actually reaches them.
3. ``pyproject.toml`` documents the tightest Playwright release so the
   default branch still matches a tested version.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


_PLAYWRIGHT_BROWSERS_VERSION_ARG = re.compile(
    r"^ARG\s+PLAYWRIGHT_BROWSERS_VERSION=(\d+|\$\{[^}]+\}|0)",
    re.MULTILINE,
)
_PLAYWRIGHT_BROWSERS_VERSION_EXPORT = re.compile(
    r"^ENV\s+PLAYWRIGHT_BROWSERS_VERSION=\$\{PLAYWRIGHT_BROWSERS_VERSION\}",
    re.MULTILINE,
)


class TestDockerfilePinsPlaywrightChromium:
    """The Dockerfile honors an explicit Chromium revision at build time."""

    def test_dockerfile_present(self) -> None:
        assert DOCKERFILE.is_file(), f"missing {DOCKERFILE}"

    def test_arg_declares_playwright_browsers_version(self) -> None:
        text = _read(DOCKERFILE)
        assert _PLAYWRIGHT_BROWSERS_VERSION_ARG.search(text), (
            "F-DOCKER-003: Dockerfile is missing"
            " ``ARG PLAYWRIGHT_BROWSERS_VERSION=0`` so Chromium"
            " can't be locked to a specific revision at build time."
        )

    def test_env_exports_playwright_browsers_version(self) -> None:
        text = _read(DOCKERFILE)
        assert _PLAYWRIGHT_BROWSERS_VERSION_EXPORT.search(text), (
            "F-DOCKER-003: Dockerfile declares ARG PLAYWRIGHT_BROWSERS_VERSION"
            " but does not export it via ENV, so ``RUN`` layers cannot read it."
            " Browsers would be re-pinned on every FROM."
        )

    def test_both_dev_and_prod_use_pinned_install(self) -> None:
        """Branches in both stages must read PLAYWRIGHT_BROWSERS_VERSION."""
        text = _read(DOCKERFILE)

        # Split the file into stages by ``FROM ... AS <name>`` boundaries,
        # then check both ``dev`` and ``production`` for the branch.
        stages: dict[str, str] = {}
        boundaries = list(
            re.finditer(
                r"^FROM\s+\S+(?:\s+AS\s+(?P<name>\S+))?",
                text,
                re.MULTILINE | re.IGNORECASE,
            )
        )
        for i, m in enumerate(boundaries):
            name = m.group("name") or f"stage_{i}"
            start = m.end()
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
            stages[name] = text[start:end]

        for stage in ("dev", "production"):
            assert stage in stages, (
                f"F-DOCKER-003: Dockerfile has no stage named ``{stage}``;"
                " cannot verify the chromium pin is honored for that target."
            )
            stage_body = stages[stage]
            assert "playwright install chromium" in stage_body, f"F-DOCKER-003: {stage} stage no longer installs chromium."
            # Every install must either honor the pin or be inside an
            # ``if [ "${PLAYWRIGHT_BROWSERS_VERSION}" = "0" ]; then``
            # branch. A bare install is the bug we're guarding.
            assert "PLAYWRIGHT_BROWSERS_VERSION" in stage_body, (
                f"F-DOCKER-003: {stage} stage runs ``playwright install"
                " chromium`` without honoring the pinned browser"
                " revision; rescue the F-DOCKER-003 reproducibility"
                " invariant by wrapping the install in an ``if`` branch."
            )

    def test_pyproject_declares_tight_playwright_pin(self) -> None:
        """``.`` pyproject must keep a tested Playwright release; otherwise
        the default install mode is on a moving target."""
        text = _read(PYPROJECT)
        assert re.search(r'"playwright[><=~!,\s\d\.]+"', text), (
            "F-DOCKER-003: pyproject.toml is missing a `playwright`"
            " pin (>=X.Y.Z, <A.B.C) so the default ``playwright install``"
            " branch can silently drift to a Playwright release with a"
            " different Chromium revision."
        )
