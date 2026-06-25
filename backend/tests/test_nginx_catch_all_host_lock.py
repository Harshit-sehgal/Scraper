"""Static guard for F-NGINX-005 — catch-all host header rejection.

Before the fix, ``nginx.conf`` listen blocks used ``server_name _;``.
nginx treats ``_`` as "match any host header that wasn't claimed by
another server", which is exactly the wrong posture for production:
an attacker can supply a malicious ``Host:`` header and FastAPI's
case-by-case routing will see it, opening host-header injection
opportunities (e.g. password-reset link poisoning or canonical-URL
generation that points to attacker domains).

Lock-in: every TLS-enabled server block in ``nginx.conf`` MUST
either:

1. Restrict ``server_name`` to the production domain, or
2. Provide a ``default_server`` sibling that ``return 444;`` (close,
   no response) any other host header.

This test is text-only; ``nginx -t`` would also catch malformed
syntax but is heavyweight and depends on a local nginx install.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"
DEFAULT_444 = re.compile(r"listen\s+\d+\s+default_server[\s\S]*?return\s+444;")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _has_444_default(path: Path) -> bool:
    """True if any default_server block in ``path`` returns 444 on bare host."""
    return bool(DEFAULT_444.search(_read(path)))


class TestNginxCatchAllHostHeaderLocked:
    """The production nginx config rejects bare Host headers with 444."""

    def test_production_nginx_conf_has_444_default(self) -> None:
        assert NGINX_CONF.is_file(), "nginx.conf missing"
        assert _has_444_default(NGINX_CONF), (
            "nginx.conf must contain a default_server sibling that returns"
            " 444 on unknown Host headers. F-NGINX-005: a bare "
            "``server_name _;`` accepts any Host header, allowing"
            " host-header injection."
        )

    def test_production_nginx_conf_no_bare_underscore_server_name(self) -> None:
        """No uncommented ``server_name _;`` may survive in nginx.conf."""
        text = _read(NGINX_CONF)
        bare = []
        for idx, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "server_name" in line:
                after = line.split("server_name", 1)[1].split(";", 1)[0]
                tokens = after.split()
                if tokens and tokens[0] == "_":
                    bare.append((idx, line))
        msg_lines = [f"  {idx}: {line}" for idx, line in bare]
        msg = "\n".join(msg_lines) if msg_lines else "none"
        assert not bare, (
            f"F-NGINX-005: nginx.conf has these bare ``server_name _;`` lines that accept arbitrary Host headers:\n{msg}"
        )
