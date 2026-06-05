"""Static guards for the nginx reverse-proxy configuration.

The repository ships a recommended HTTPS-first deployment. This test
ensures the configuration does not regress to the prior design where
HSTS was emitted on the plain-HTTP server (browsers ignore HSTS over
HTTP — see MDN — and emitting it there is misleading).

Rules:

1. The HTTP listen block MUST NOT set ``Strict-Transport-Security``.
2. An HTTPS listen block MUST set ``Strict-Transport-Security`` when
   the production posture is "TLS-first".
3. The HTTP block SHOULD redirect to HTTPS (return 301) for any path
   other than ACME challenges and liveness probes.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"


def _strip_comments(text: str) -> str:
    """Remove ``#`` line comments so commented-out blocks don't count."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def _iter_active_server_blocks(text: str):
    """Yield each un-commented ``server { ... }`` block as a string."""
    text = _strip_comments(text)
    # find every "server {" then walk braces to find the matching close
    i = 0
    while True:
        m = re.search(r"\bserver\s*\{", text[i:])
        if not m:
            return
        start = i + m.start()
        depth = 0
        j = start
        while j < len(text):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : j + 1]
                    i = j + 1
                    break
            j += 1
        else:
            return


def test_nginx_conf_exists() -> None:
    assert NGINX_CONF.exists(), f"nginx.conf not found at {NGINX_CONF}"


def test_http_server_does_not_emit_hsts() -> None:
    """HSTS MUST NOT appear on a server that listens on port 80 only."""
    text = NGINX_CONF.read_text()
    for block in _iter_active_server_blocks(text):
        listen_match = re.search(r"\blisten\s+([^;{]+);", block)
        if not listen_match:
            continue
        listen_directives = listen_match.group(1)
        # Only flag pure-HTTP listeners (no ssl/http2).
        if "ssl" in listen_directives or "443" in listen_directives:
            continue
        if "Strict-Transport-Security" in block:
            raise AssertionError(
                "HTTP server block sets Strict-Transport-Security. "
                "Browsers ignore HSTS over plain HTTP — move it to the "
                "HTTPS (ssl) block. Offending block:\n" + block,
            )


def test_https_server_emits_hsts() -> None:
    """The TLS server block MUST set Strict-Transport-Security."""
    text = NGINX_CONF.read_text()
    found_tls = False
    found_hsts = False
    for block in _iter_active_server_blocks(text):
        listen_match = re.search(r"\blisten\s+([^;{]+);", block)
        if not listen_match:
            continue
        if "ssl" in listen_match.group(1) or "443" in listen_match.group(1):
            found_tls = True
            if "Strict-Transport-Security" in block:
                found_hsts = True
    assert found_tls, "No active HTTPS server block found in nginx.conf"
    assert found_hsts, "Active HTTPS server block is missing Strict-Transport-Security"


def test_http_block_redirects_or_handles_acme() -> None:
    """The HTTP block should either 301 to HTTPS or service ACME+probes."""
    text = NGINX_CONF.read_text()
    for block in _iter_active_server_blocks(text):
        listen_match = re.search(r"\blisten\s+([^;{]+);", block)
        if not listen_match:
            continue
        if "ssl" in listen_match.group(1) or "443" in listen_match.group(1):
            continue
        # Plain HTTP block must either redirect, or limit to acme/health.
        redirects = re.search(r"return\s+301\s+https://", block)
        if redirects:
            continue
        # Else: a dev / HTTP-only block — make sure it doesn't try to be
        # the production path (no real upstream proxies without TLS).
        if "/.well-known/acme-challenge" in block and ("/health" in block or "/ready" in block):
            continue
        raise AssertionError(
            "Plain-HTTP server block neither redirects to HTTPS nor "
            "limits itself to ACME/probes. Add `return 301 https://$host$request_uri;` "
            "or restrict to challenge paths. Block:\n" + block,
        )
