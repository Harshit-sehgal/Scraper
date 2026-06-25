"""Static guards for the F-DOCKER-006 nginx landing-alias filesystem leak.

Regression target:
    - F-DOCKER-006 (P2): the ``location /landing/ { alias ... }`` block
      serves files under ``/usr/share/nginx/html/frontend/landing/``.
      If ``frontend/`` is from an operator-deployed dev build, that
      directory may contain ``.git/``, ``.env``, ``.docker``, or
      ``.aws`` configuration. The alias must explicitly deny those
      paths so they cannot be reached by prefixing the URL.

The fix commits nested locations inside ``/landing/``:

    location /landing/ {
        alias /usr/share/nginx/html/frontend/landing/;
        location ~ /\\.(git|env|docker|aws) { deny all; return 404; }
    }

This test verifies the production ``nginx.conf`` and the local dev
override ``nginx.local.conf`` both ship the lockdown. Localization is
required so the regression cannot survive in dev silently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"
NGINX_LOCAL = REPO_ROOT / "nginx.local.conf"

# Targets one of the four forbidden dotfile segments inside the
# matched-list ``|``. The presence of a backslash before the dot is
# nginx-quoted as ``\.`` (regex meta-escape) or ``\\.`` (doubled during
# templating). Both are valid nginx invocations, so we accept either.
_DOTFILE_REGEX = re.compile(
    r"location\s+~?\s*/\\*?\.\(git\|env\|docker\|aws\)\s*\{[^{}]*?\n"
    r"[^{}]*?deny\s+all;[^{}]*?return\s+404[^{}]*?\}",
    flags=re.DOTALL,
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_production_landing_alias_locks_down_dotfiles() -> None:
    text = _read(NGINX_CONF)
    assert "/landing/" in text, f"expected `location /landing/` block in {NGINX_CONF}"
    assert _DOTFILE_REGEX.search(text), (
        "production nginx.conf: missing the .git/.env/.docker/.aws deny block."
        " F-DOCKER-006: an operator-deployed dev build of frontend/ could leak"
        " .git/config via the /landing/ alias."
    )


def test_local_landing_alias_locks_down_dotfiles() -> None:
    text = _read(NGINX_LOCAL)
    assert "/landing/" in text, f"expected `location /landing/` block in {NGINX_LOCAL}"
    assert _DOTFILE_REGEX.search(text), (
        "local nginx.local.conf: missing the .git/.env/.docker/.aws deny block."
        " F-DOCKER-006: keep dev and prod aligned so the path-traversal"
        " regression cannot survive in dev."
    )


def test_landing_lockdown_uses_404_not_403() -> None:
    """``return 404`` (not 403) avoids leaking directory existence."""
    for path in (NGINX_CONF, NGINX_LOCAL):
        text = _read(path)
        m = _DOTFILE_REGEX.search(text)
        assert m, f"{path}: missing lockdown block; cannot verify 404"
        block = m.group(0)
        assert "return 404" in block, f"{path}: lockdown must use `return 404`"
        # ``return 403`` would tell an attacker the directory exists.
        assert "return 403" not in block, (
            f"{path}: lockdown must not use `return 403`; that exposes directory existence to attackers."
        )


def test_landing_lockdown_lists_four_targets() -> None:
    """All four forbidden subpaths (``git``, ``env``, ``docker``, ``aws``)."""
    for path in (NGINX_CONF, NGINX_LOCAL):
        text = _read(path)
        m = _DOTFILE_REGEX.search(text)
        assert m, f"{path}: missing lockdown block"
        block = m.group(0)
        for label in ("git", "env", "docker", "aws"):
            assert label in block, f"{path}: lockdown regex must list {label!r} so .env, .git, etc. are all forbidden"
