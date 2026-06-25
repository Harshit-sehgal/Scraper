"""Static guard for F-NGINX-006 — nginx keep-alive request cap.

Regression target:
    - F-NGINX-006 (P2): nginx defaulted ``keepalive_requests`` by
      version, leaving production capacity sensitive to the nginx image
      default instead of the project's intended connection lifetime.

Lock-in: production ``nginx.conf`` must pin ``keepalive_requests`` to
10000 in the active ``http`` context so client keep-alive reuse does not
silently drift with nginx defaults.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"


def _active_text() -> str:
    assert NGINX_CONF.is_file(), f"missing {NGINX_CONF}"
    lines = []
    for line in NGINX_CONF.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_keepalive_requests_is_explicitly_pinned() -> None:
    text = _active_text()
    values = re.findall(r"^\s*keepalive_requests\s+(\d+);", text, flags=re.MULTILINE)
    assert values == ["10000"], (
        f"nginx.conf must pin exactly one active `keepalive_requests 10000;` directive for F-NGINX-006 (found: {values!r})."
    )


def test_keepalive_requests_is_in_http_context_before_servers() -> None:
    text = _active_text()
    http_idx = text.find("http {")
    keepalive_idx = text.find("keepalive_requests 10000;")
    server_idx = text.find("server {")
    assert http_idx != -1, "nginx.conf missing active `http {` block"
    assert keepalive_idx != -1, "nginx.conf missing active `keepalive_requests 10000;`"
    assert server_idx != -1, "nginx.conf missing active `server {` block"
    assert http_idx < keepalive_idx < server_idx, (
        "`keepalive_requests 10000;` must live in the active http context before"
        " server blocks so it applies consistently across production listeners."
    )
