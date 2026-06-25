"""Static guard for F-NGINX-006 — keepalive_requests pinning.

Lock-in: nginx's default ``keepalive_requests`` changed across
versions (100 in 1.19.7, 1000 in 1.25.x, etc.). The default is too
low for a long-poll-driven crawler like DataForge: a single client
re-cycling the same TCP connection 1000+ times can be silently
disconnected mid-job.

The fix is an explicit ``keepalive_requests`` directive in the
``http {}`` block of ``nginx.conf``. This test asserts that the
directive is present and that the value is at least 1000 so we are
never accidentally below the most recent default.

This is text-only; ``nginx -t`` would also catch malformed syntax but
is heavyweight and depends on a local nginx install.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"

_PIN = re.compile(r"keepalive_requests[\s:]+(?P<value>\d+)\s*;")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


class TestNginxKeepaliveRequestsPinned:
    """Production nginx has an explicit ``keepalive_requests`` directive."""

    def test_nginx_conf_has_keepalive_requests(self) -> None:
        text = _read(NGINX_CONF)
        m = _PIN.search(text)
        assert m, (
            "nginx.conf must set ``keepalive_requests`` explicitly."
            " F-NGINX-006: relying on the upstream default means"
            " a silent bump across nginx releases could"
            " prematurely close long-poll connections."
        )

    def test_keepalive_requests_value_is_sane(self) -> None:
        text = _read(NGINX_CONF)
        m = _PIN.search(text)
        assert m
        value = int(m.group("value"))
        # Must be at least 1000 — never accidentally drop below the
        # post-1.25.x default of 1000.
        assert value >= 1000, (
            f"nginx.conf keepalive_requests={value} is below the"
            " F-NGINX-006 floor of 1000. A higher value is acceptable"
            " (10_000 is recommended); a lower value regresses the"
            " default-on-recent-nginx posture."
        )
