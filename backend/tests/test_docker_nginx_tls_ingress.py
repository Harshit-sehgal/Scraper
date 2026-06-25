"""Guards for the production compose/nginx TLS ingress contract.

The active production ``nginx.conf`` contains HTTPS listeners and the
plain HTTP listener redirects to HTTPS. The production Compose file and
smoke script must therefore provide a runnable 443 ingress path instead
of probing the app over cleartext.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_prod_stack.sh"


def _compose() -> dict[str, Any]:
    assert PROD_COMPOSE.is_file(), f"missing {PROD_COMPOSE}"
    return yaml.safe_load(PROD_COMPOSE.read_text(encoding="utf-8"))


def _nginx_service() -> dict[str, Any]:
    services = _compose()["services"]
    assert "nginx" in services, "production compose missing nginx service"
    return services["nginx"]


def test_prod_compose_publishes_http_and_https_ingress_ports() -> None:
    ports = [str(port) for port in _nginx_service().get("ports", [])]

    assert any(port.endswith(":80") and "HTTP_PORT" in port for port in ports), (
        "docker-compose.prod.yml nginx service must publish container port 80 through "
        "an explicit HTTP_PORT variable so ACME and redirects remain reachable."
    )
    assert any(port.endswith(":443") and "HTTPS_PORT" in port for port in ports), (
        "docker-compose.prod.yml nginx service must publish container port 443 through "
        "an explicit HTTPS_PORT variable because the active production nginx.conf serves HTTPS."
    )
    assert "${HOST:-0.0.0.0}:${PORT:-80}:80" not in ports, (
        "production nginx ingress must not reuse the generic PORT variable; .env uses PORT for "
        "the development app server and can silently bind nginx to the wrong host port."
    )


def test_prod_compose_mounts_nginx_tls_certificate_and_acme_webroot() -> None:
    volumes = [str(volume) for volume in _nginx_service().get("volumes", [])]

    assert any("DATAFORGE_NGINX_SSL_DIR" in volume and ":/etc/nginx/ssl:ro" in volume for volume in volumes), (
        "production nginx.conf references /etc/nginx/ssl/fullchain.pem and privkey.pem; "
        "docker-compose.prod.yml must mount the operator-provided TLS directory."
    )
    assert any("DATAFORGE_CERTBOT_WEBROOT" in volume and ":/var/www/certbot:ro" in volume for volume in volumes), (
        "the HTTP listener leaves /.well-known/acme-challenge/ on cleartext; "
        "docker-compose.prod.yml must mount the ACME webroot used by nginx.conf."
    )


def test_prod_smoke_uses_https_ingress_by_default() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "SMOKE_HTTPS_PORT" in text
    assert "https://localhost" in text
    assert "SMOKE_CURL_ARGS" in text
    assert "fullchain.pem" in text
    assert "privkey.pem" in text
    assert 'curl -s "${SMOKE_CURL_ARGS[@]}"' in text
    assert 'SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost' not in text
