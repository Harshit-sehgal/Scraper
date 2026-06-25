"""Guard tests for nginx rate-limit coverage.

These tests inspect ``nginx.conf`` and ``nginx.local.conf`` as text.
They are the F-NGINX-003 regression suite so a future refactor that
drops the rate-limit on ``/dashboard/`` does not silently re-open
the path-normalization bypass.

F-NGINX-003 (P0) regression: prior to the fix, ``/dashboard/``
proxied with ``proxy_pass http://dataforge_api;`` and no
``limit_req``. nginx normalises ``..`` segments during location
matching, so ``/dashboard/../api/admin/foo`` was matched by the
``/dashboard/`` prefix and forwarded upstream as ``/api/admin/foo``
bypassing the ``/api/`` rate-limit zone. Anyone reaching the proxy
could hammer ``/api/admin/*`` at unbounded rate.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/tests/X.py → repo root
NGINX_CONF = REPO_ROOT / "nginx.conf"
NGINX_LOCAL_CONF = REPO_ROOT / "nginx.local.conf"


def _active_server_block(text: str) -> str:
    """Return the active app-serving HTTPS server block.

    nginx config comments are ``# ...`` at the start of any line. Server
    block C is intentionally commented out in ``nginx.conf``. The first
    active server block may be the default 444 unknown-host sink, so we
    select the active server block that owns ``/dashboard/``.

    The capture walks the chars from ``^\\s*server {`` and balances
    braces (since server blocks contain nested ``location {}`` blocks).
    """
    block_starts = [m.start() for m in re.finditer(r"^[ \t]*server\s*\{", text, re.MULTILINE)]
    assert block_starts, "nginx.conf has no active server block"
    for start in block_starts:
        body_start = text.index("{", start)
        depth = 0
        for i in range(body_start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body = text[body_start + 1 : i]
                    if "location /dashboard/" in body:
                        return body
                    break
    msg = "nginx.conf: server block never balances"
    raise AssertionError(msg)


def _location_block(server_block: str, prefix: str) -> str:
    """Return the text inside ``location {prefix}{...}`` for an exact prefix match."""
    pattern = r"location\s+" + re.escape(prefix) + r"\s*\{(?P<body>[^}]*)\}"
    m = re.search(pattern, server_block)
    assert m, f"{prefix!r} location block not found"
    return m.group("body")


def _nginx_local_dashboard_block() -> str:
    """``nginx.local.conf`` only has one server block; extract the ``/dashboard/`` location."""
    text = NGINX_LOCAL_CONF.read_text(encoding="utf-8")
    assert NGINX_LOCAL_CONF.is_file(), f"missing {NGINX_LOCAL_CONF}"
    return _location_block(text, "/dashboard/")


# ---------------------------------------------------------------------------
# F-NGINX-003 — dashboard must apply the same limit_req as /api/
# ---------------------------------------------------------------------------


class TestDashboardRateLimitApplied:
    """The ``/dashboard/`` location block declares the api zone limit_req."""

    def test_prod_nginx_dashboard_has_limit_req(self) -> None:
        text = NGINX_CONF.read_text(encoding="utf-8")
        assert NGINX_CONF.is_file(), f"missing {NGINX_CONF}"
        block = _location_block(_active_server_block(text), "/dashboard/")
        # F-NGINX-003: accept either ``zone=api`` (legacy static) or
        # ``zone=$api_bucket`` (F-NGINX-SEC-001 method-aware bucket —
        # GETs land in the read ``api`` zone; writes in ``api_write``).
        # Both bristle against the path-normalization bypass: ``GET
        # /dashboard/../api/admin/...`` still throttled, ``POST
        # /dashboard/../api/admin/...`` throttled by the write bucket.
        # The dashboard block MUST share the same per-method throttle
        # as ``/api/`` so an attacker cannot pivot through
        # ``/dashboard/`` to evade the API throttle.
        assert re.search(r"limit_req\s+zone=\S+", block), (
            "nginx.conf: /dashboard/ location no longer applies a limit_req;"
            " the F-NGINX-003 path-normalization bypass is back."
        )
        assert ("zone=api" in block) or ("zone=$api_bucket" in block), (
            "nginx.conf: /dashboard/ does not share a rate-limit zone with"
            " /api/; the F-NGINX-003 path-normalization bypass"
            " (/dashboard/../api/admin/) is exploitable again."
        )

    def test_local_nginx_dashboard_has_limit_req(self) -> None:
        block = _nginx_local_dashboard_block()
        assert re.search(r"limit_req\s+zone=\S+", block), (
            "nginx.local.conf: /dashboard/ location no longer applies a limit_req;"
            " the F-NGINX-003 path-normalization bypass is back."
        )
        assert ("zone=api" in block) or ("zone=$api_bucket" in block), (
            "nginx.local.conf: /dashboard/ does not share a rate-limit zone with"
            " /api/; the F-NGINX-003 bypass is exploitable in the local stack."
        )


class TestProdServerBlockOnlyOneActiveDashboardLocation:
    """The production server block A hosts exactly one ``/dashboard/`` location.

    A regression that adds a second ``/dashboard/`` block under a different
    prefix (``location = /dashboard`` etc.) can be valid, but the prefix
    location that matches ``/dashboard/../api/...`` must keep its
    ``limit_req``.
    """

    def test_only_one_dashboard_location_in_prod_https_block(self) -> None:
        text = NGINX_CONF.read_text(encoding="utf-8")
        block = _active_server_block(text)
        count = len(re.findall(r"location\s+/dashboard/", block))
        assert count == 1, f"nginx.conf: expected exactly one ``location /dashboard/`` in the active server block, found {count}"
