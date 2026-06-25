"""Static guard for F-NGINX-SEC-001 — per-method API rate limiting.

Pre-fix, the production ``nginx.conf`` and ``nginx.local.conf`` both
defined a single ``limit_req zone=api burst=20 nodelay`` for ``/api/``,
treating reads and writes identically. Reads are bounded by the
dashboard's natural polling cadence so a generous rate is fine, but
writes (``POST/PUT/PATCH/DELETE``) trade off against the storage
backend's write throughput. A sweeping flood of writes therefore
needs a stricter throttle at the proxy so the backend can fail
closed rather than melt.

Lock-in:

1. The ``http {}`` context MUST define **two** ``limit_req_zone``
   directives:
   - ``zone=api`` for the read bucket
   - ``zone=api_write`` for the write bucket
2. A ``map $request_method`` block must classify ``POST/PUT/PATCH/
   DELETE`` into the write zone and everything else into the read
   zone.
3. The ``/api/`` location block must apply ``limit_req
   zone=$api_bucket ...`` (dynamic per-method assignment) rather
   than a literal ``zone=api`` that ignores writes.

This is text-only; ``nginx -t`` would also catch malformed syntax but
is heavyweight and depends on a local nginx install.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONFIGS = (
    REPO_ROOT / "nginx.conf",
    REPO_ROOT / "nginx.local.conf",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


_MAP_BLOCK = re.compile(
    r"map\s+\$request_method\s+\$api_bucket\s*\{(?P<body>[^}]*)\}",
    re.MULTILINE,
)
_API_ZONE = re.compile(r"limit_req_zone\s+\$binary_remote_addr\s+zone=[\"']?api[\"']?:")
_WRITE_ZONE = re.compile(r"limit_req_zone\s+\$binary_remote_addr\s+zone=[\"']?api_write[\"']?:")
_API_LOCATION_DYNAMIC = re.compile(
    r"location\s+/api/\s*\{[^{}]*?\n[^{}]*?limit_req\s+zone=\$api_bucket",
    re.MULTILINE,
)
_API_LOCATION_STATIC = re.compile(
    r"location\s+/api/\s*\{[^{}]*?\n[^{}]*?limit_req\s+zone=api\b",
    re.MULTILINE,
)


def _strip_commented_out_locations(text: str) -> str:
    """Remove ``location … { … }`` blocks whose opening line is commented.

    nginx.conf carries commented-out reference blocks under
    ``# F-NGINX-...`` notes; we don't want those to trip the
    ``no static zone=api`` assertion below.
    """
    out_lines: list[str] = []
    in_block = False
    skip_block = False
    for line in text.splitlines():
        if not in_block:
            stripped = line.lstrip()
            if stripped.startswith("#") and "location" in stripped and "{" in stripped:
                # Commented-out block start.
                in_block = True
                skip_block = True
                continue
            out_lines.append(line)
            continue
        # inside a block; track braces
        if skip_block:
            if "}" in line:
                in_block = False
                skip_block = False
            continue
        # Not expected — fallback: append and reset.
        out_lines.append(line)
        in_block = False
    return "\n".join(out_lines)


def _map_zone_for_write(text: str) -> bool:
    m = _MAP_BLOCK.search(text)
    if not m:
        return False
    body = m.group("body")
    # All four write methods must end up in ``api_write``.
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        line = next(
            (line.strip() for line in body.splitlines() if method in line and line.strip().lower().startswith(method.lower())),
            "",
        )
        if "api_write" not in line:
            return False
    return True


class TestNginxWriteMethodRateLimit:
    """Write methods are throttled at a stricter bucket than reads."""

    def test_production_nginx_conf_has_api_and_api_write_zones(self) -> None:
        text = _read(REPO_ROOT / "nginx.conf")
        assert _API_ZONE.search(text), "nginx.conf must define ``limit_req_zone`` for ``api``. F-NGINX-SEC-001."
        assert _WRITE_ZONE.search(text), (
            "nginx.conf must define ``limit_req_zone`` for"
            " ``api_write``. F-NGINX-SEC-001: the read-bucket-only"
            " posture exposes writes to floods."
        )

    def test_local_override_has_api_and_api_write_zones(self) -> None:
        path = REPO_ROOT / "nginx.local.conf"
        if not path.is_file():
            return  # Local override is optional.
        text = _read(path)
        assert _API_ZONE.search(text)
        assert _WRITE_ZONE.search(text), (
            "nginx.local.conf is the developer-facing mirror and must follow the same F-NGINX-SEC-001 throttle posture."
        )

    def test_method_map_routes_writes_to_strict_zone(self) -> None:
        for path in NGINX_CONFIGS:
            if not path.is_file():
                continue
            text = _read(path)
            assert _MAP_BLOCK.search(text), (
                f"{path.name}: must define ``map $request_method"
                " $api_bucket`` so the limit_req lookup can pick the"
                " right zone per verb. F-NGINX-SEC-001."
            )
            assert _map_zone_for_write(text), (
                f"{path.name}: every flow-modifying verb in the map body must map to ``api_write``. F-NGINX-SEC-001."
            )

    def test_api_location_uses_dynamic_bucket(self) -> None:
        for path in NGINX_CONFIGS:
            if not path.is_file():
                continue
            text = _strip_commented_out_locations(_read(path))
            assert _API_LOCATION_DYNAMIC.search(text), (
                f"{path.name}: ``/api/`` location block must apply"
                " ``limit_req zone=$api_bucket ...`` so the"
                " write-method throttle is actually engaged."
                " F-NGINX-SEC-001 forbids the static ``zone=api``"
                " form here because it ignores writes."
            )
            # The static form indicates someone reverted to the
            # pre-fix posture.
            assert not _API_LOCATION_STATIC.search(text), (
                f"{path.name}: ``/api/`` location block still has the"
                " static ``limit_req zone=api`` form. This is the"
                " F-NGINX-SEC-001 regression path: writes go through"
                " the read bucket and the stricter throttle is"
                " silently disabled."
            )
