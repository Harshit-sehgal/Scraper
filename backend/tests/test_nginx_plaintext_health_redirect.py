"""Static guard for F-NGINX-002 — no plaintext health proxying."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"


def _active_text() -> str:
    assert NGINX_CONF.is_file(), f"missing {NGINX_CONF}"
    return "\n".join(line for line in NGINX_CONF.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))


def _iter_server_blocks(text: str):
    start = 0
    while True:
        match = re.search(r"\bserver\s*\{", text[start:])
        if match is None:
            return
        block_start = start + match.start()
        body_start = text.index("{", block_start)
        depth = 0
        for idx in range(body_start, len(text)):
            char = text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[block_start : idx + 1]
                    start = idx + 1
                    break
        else:
            msg = "nginx.conf has an unbalanced server block"
            raise AssertionError(msg)


def _production_http_server() -> str:
    for block in _iter_server_blocks(_active_text()):
        if re.search(r"\blisten\s+80\s+default_server\s*;", block) and "server_name dataforge.example.com" in block:
            return block
    msg = "missing production HTTP `listen 80 default_server` block"
    raise AssertionError(msg)


def _location_body(server_block: str, location: str) -> str:
    pattern = r"location\s+" + re.escape(location) + r"\s*\{(?P<body>[^{}]*)\}"
    match = re.search(pattern, server_block, flags=re.DOTALL)
    assert match, f"missing `location {location}` in production HTTP server block"
    return match.group("body")


def test_plain_http_health_and_ready_redirect_to_https() -> None:
    server = _production_http_server()
    for location in ("= /health", "= /ready"):
        body = _location_body(server, location)
        assert "proxy_pass" not in body, (
            f"F-NGINX-002: `location {location}` must not proxy plaintext health traffic to the app. Redirect to HTTPS instead."
        )
        assert re.search(r"return\s+301\s+https://\$host\$request_uri\s*;", body), (
            f"F-NGINX-002: `location {location}` must redirect to HTTPS with `return 301 https://$host$request_uri;`."
        )


def test_plain_http_acme_challenge_remains_available() -> None:
    server = _production_http_server()
    acme_body = _location_body(server, "/.well-known/acme-challenge/")
    assert "root /var/www/certbot;" in acme_body
    assert "return 301" not in acme_body
    assert "proxy_pass" not in acme_body
