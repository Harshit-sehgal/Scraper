"""Static guard for F-NGINX-005 — production unknown-host lockdown.

Regression target:
    - F-NGINX-005 (P2): production ``nginx.conf`` used
      ``server_name _;`` on the HTTPS app server, so any attacker-supplied
      Host header reaching nginx was passed through to FastAPI.

Lock-in: production nginx must have a dedicated 443 default server that
returns 444 for unknown hosts, while app-serving server blocks must use
an explicit host name instead of the wildcard ``_``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"


def _read() -> str:
    assert NGINX_CONF.is_file(), f"missing {NGINX_CONF}"
    return NGINX_CONF.read_text(encoding="utf-8")


def _active_lines(text: str) -> list[str]:
    """Return nginx source lines with full-line comments removed."""
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_production_https_has_default_unknown_host_sink() -> None:
    text = _read()
    block = re.search(
        r"server\s*\{(?P<body>[^{}]*?listen\s+443\s+default_server\s+ssl;[^{}]*?return\s+444;[^{}]*?)\}",
        text,
        flags=re.DOTALL,
    )
    assert block, (
        "nginx.conf must define a 443 default_server block that returns 444"
        " so unknown Host headers are closed before reaching FastAPI (F-NGINX-005)."
    )


def test_production_app_servers_do_not_use_wildcard_server_name() -> None:
    text = "\n".join(_active_lines(_read()))
    wildcard = re.findall(r"^\s*server_name\s+_;\s*$", text, flags=re.MULTILINE)
    assert not wildcard, (
        "nginx.conf still contains an active `server_name _;` directive."
        " F-NGINX-005 requires explicit app hostnames plus a default 444 sink."
    )


def test_production_app_server_declares_explicit_host_name() -> None:
    text = "\n".join(_active_lines(_read()))
    names = re.findall(r"^\s*server_name\s+([^;]+);\s*(?:#.*)?$", text, flags=re.MULTILINE)
    assert names, "nginx.conf must declare at least one active explicit server_name"
    assert any(name.strip() not in {"_", ""} for name in names), (
        "nginx.conf must include an explicit application server_name;"
        " `server_name _;` is not an acceptable production host match."
    )
