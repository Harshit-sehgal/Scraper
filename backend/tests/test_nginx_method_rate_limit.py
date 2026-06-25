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

1. The ``http {}`` context MUST define separate request keys:
   - ``$api_read_key`` is populated for read methods only.
   - ``$api_write_key`` is populated for write methods only.
2. The two ``limit_req_zone`` directives must use those keys, with
   ``zone=api`` for reads and ``zone=api_write`` for writes.
3. The ``/api/`` location block must apply both static zones.

nginx does not support variables in the ``limit_req zone=...`` name.
The invalid ``zone=$api_bucket`` form passes naive text tests but
fails ``nginx -t`` at runtime.
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


_READ_MAP_BLOCK = re.compile(
    r"map\s+\$request_method\s+\$api_read_key\s*\{(?P<body>[^}]*)\}",
    re.MULTILINE,
)
_WRITE_MAP_BLOCK = re.compile(
    r"map\s+\$request_method\s+\$api_write_key\s*\{(?P<body>[^}]*)\}",
    re.MULTILINE,
)
_API_ZONE = re.compile(r"limit_req_zone\s+\$api_read_key\s+zone=[\"']?api[\"']?:")
_WRITE_ZONE = re.compile(r"limit_req_zone\s+\$api_write_key\s+zone=[\"']?api_write[\"']?:")
_DYNAMIC_LIMIT_ZONE = re.compile(r"limit_req\s+zone=\$")


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


def _method_line(body: str, method: str) -> str:
    return next(
        (line.strip() for line in body.splitlines() if method in line and line.strip().lower().startswith(method.lower())),
        "",
    )


def _is_empty_key(value: str) -> bool:
    return '""' in value or "''" in value


def _map_keys_for_method_buckets(text: str) -> bool:
    read_match = _READ_MAP_BLOCK.search(text)
    write_match = _WRITE_MAP_BLOCK.search(text)
    if not read_match or not write_match:
        return False

    read_body = read_match.group("body")
    write_body = write_match.group("body")
    if "default $binary_remote_addr;" not in read_body:
        return False
    if not _is_empty_key(_method_line(write_body, "default")):
        return False

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        if not _is_empty_key(_method_line(read_body, method)):
            return False
        if "$binary_remote_addr" not in _method_line(write_body, method):
            return False
    return True


def _location_body(text: str, location: str) -> str:
    pattern = r"location\s+" + re.escape(location) + r"\s*\{(?P<body>[^{}]*)\}"
    match = re.search(pattern, text, flags=re.DOTALL)
    assert match, f"missing `location {location}` block"
    return match.group("body")


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

    def test_method_maps_populate_only_one_bucket_per_request(self) -> None:
        for path in NGINX_CONFIGS:
            if not path.is_file():
                continue
            text = _read(path)
            assert _map_keys_for_method_buckets(text), (
                f"{path.name}: must define $api_read_key and $api_write_key maps"
                " so each request is counted in exactly one method-aware"
                " limit_req_zone. F-NGINX-SEC-001."
            )

    def test_api_location_applies_both_static_buckets(self) -> None:
        for path in NGINX_CONFIGS:
            if not path.is_file():
                continue
            text = _strip_commented_out_locations(_read(path))
            body = _location_body(text, "/api/")
            assert "limit_req zone=api burst=20 nodelay;" in body, f"{path.name}: ``/api/`` must apply the read throttle zone."
            assert "limit_req zone=api_write burst=10 nodelay;" in body, (
                f"{path.name}: ``/api/`` must apply the stricter write throttle zone."
            )
            assert not _DYNAMIC_LIMIT_ZONE.search(body), (
                f"{path.name}: nginx rejects variable zone names such as ``zone=$api_bucket`` at runtime."
            )
