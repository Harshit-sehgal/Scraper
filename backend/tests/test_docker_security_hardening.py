"""F-DOCKER-CAPABILITIES-001 / F-NGINX-HEALTHCHECK-001 / F-PROM-HEALTHCHECK-001.

Verifies container hardening across the production compose file. The
tests parse ``docker-compose.prod.yml`` so they fail loudly in CI when
someone removes a security control without updating the test guards.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.prod.yml"


def _load_compose() -> dict:
    assert COMPOSE_PATH.is_file(), f"missing compose file at {COMPOSE_PATH}"
    with open(COMPOSE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestCapabilityDrops:
    """Every external-facing service must drop NET_RAW (and friends)."""

    def test_postgres_drops_net_raw(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["postgres"]
        caps = svc.get("cap_drop") or []
        assert "NET_RAW" in caps, "postgres must drop NET_RAW capability"

    def test_nginx_drops_all_caps(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["nginx"]
        caps = svc.get("cap_drop") or []
        assert "ALL" in caps, "nginx must drop ALL capabilities"

    def test_node_exporter_drops_net_raw(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["node-exporter"]
        caps = svc.get("cap_drop") or []
        assert "NET_RAW" in caps, "node-exporter must drop NET_RAW"

    def test_cadvisor_drops_net_raw(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["cadvisor"]
        caps = svc.get("cap_drop") or []
        assert "NET_RAW" in caps, "cadvisor must drop NET_RAW"

    def test_prometheus_drops_net_raw(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["prometheus"]
        caps = svc.get("cap_drop") or []
        assert "NET_RAW" in caps, "prometheus must drop NET_RAW"
        assert svc.get("security_opt") == ["no-new-privileges:true"], "prometheus must have no-new-privileges:true"

    def test_grafana_drops_net_raw(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["grafana"]
        caps = svc.get("cap_drop") or []
        assert "NET_RAW" in caps, "grafana must drop NET_RAW"

    def test_blackbox_exporter_drops_net_raw(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["blackbox-exporter"]
        caps = svc.get("cap_drop") or []
        assert "NET_RAW" in caps, "blackbox-exporter must drop NET_RAW"


class TestHealthchecks:
    """Every external-facing service must have a healthcheck."""

    def test_nginx_has_healthcheck(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["nginx"]
        assert "healthcheck" in svc, "nginx must have a healthcheck"

    def test_prometheus_has_healthcheck(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["prometheus"]
        assert "healthcheck" in svc, "prometheus must have a healthcheck"

    def test_grafana_has_healthcheck(self) -> None:
        compose = _load_compose()
        svc = compose["services"]["grafana"]
        assert "healthcheck" in svc, "grafana must have a healthcheck"


class TestSecurityOpts:
    """Every external-facing service must have no-new-privileges:true."""

    def test_all_services_no_new_privileges(self) -> None:
        compose = _load_compose()
        required_services = [
            "postgres",
            "nginx",
            "node-exporter",
            "cadvisor",
            "prometheus",
            "grafana",
            "blackbox-exporter",
        ]
        for svc_name in required_services:
            svc = compose["services"][svc_name]
            opts = svc.get("security_opt") or []
            assert "no-new-privileges:true" in opts, f"{svc_name} must have security_opt: no-new-privileges:true"
