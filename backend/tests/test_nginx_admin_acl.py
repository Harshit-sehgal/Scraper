"""Static guard for F-NGINX-001 — reserved admin API paths at nginx.

Regression target:
    - F-NGINX-001 (P1): nginx's generic ``location /api/`` proxy means
      future sensitive admin routes under ``/api/admin`` or
      ``/api/system/admin`` would be exposed by the edge proxy in the
      local HTTP-only stack before any reverse-proxy ACL could help.

Lock-in: both production and local nginx configs must reserve these
admin path prefixes with direct ``return 404`` blocks, and those blocks
must not proxy to FastAPI.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"
NGINX_LOCAL = REPO_ROOT / "nginx.local.conf"

RESERVED_ADMIN_LOCATIONS = (
    r"= /api/admin",
    r"/api/admin/",
    r"= /api/system/admin",
    r"/api/system/admin/",
)


def _active_text(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _location_body(text: str, location: str) -> str:
    pattern = r"location\s+" + re.escape(location) + r"\s*\{(?P<body>[^{}]*)\}"
    m = re.search(pattern, text, flags=re.DOTALL)
    assert m, f"missing active `location {location}` block"
    return m.group("body")


def test_reserved_admin_paths_are_blocked_in_all_nginx_configs() -> None:
    for path in (NGINX_CONF, NGINX_LOCAL):
        text = _active_text(path)
        for location in RESERVED_ADMIN_LOCATIONS:
            body = _location_body(text, location)
            assert re.search(r"\breturn\s+404\s*;", body), (
                f"{path}: `location {location}` must return 404 so reserved"
                " admin paths do not reach FastAPI through the generic /api/ proxy."
            )
            assert "proxy_pass" not in body, f"{path}: `location {location}` must not proxy reserved admin paths upstream."


def test_admin_acl_blocks_precede_generic_api_proxy_for_readability() -> None:
    """Prefix matching would still work, but keep the guard before /api/."""
    for path in (NGINX_CONF, NGINX_LOCAL):
        text = _active_text(path)
        api_match = re.search(r"location\s+/api/\s*\{", text)
        assert api_match, f"{path}: missing generic `location /api/` block"
        for location in RESERVED_ADMIN_LOCATIONS:
            loc_idx = text.find(f"location {location}")
            assert loc_idx != -1, f"{path}: missing `location {location}` block"
            assert loc_idx < api_match.start(), (
                f"{path}: `location {location}` should be placed before"
                " generic `location /api/` so reviewers see the reserved-path guard first."
            )
