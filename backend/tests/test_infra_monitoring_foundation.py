"""Static regression guards for deployment config foundation issues."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "nginx.conf"
NGINX_SECURITY_HEADERS = REPO_ROOT / "nginx" / "security_headers.conf"
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
PROMETHEUS = REPO_ROOT / "prometheus.yml"
PROMETHEUS_ALERTS = REPO_ROOT / "prometheus_alerts.yml"
PROMETHEUS_WEB = REPO_ROOT / "prometheus_web.yml"
STORAGE_MIGRATIONS = REPO_ROOT / "backend" / "app" / "storage_migrations.py"
POSTGRES_MIGRATION = REPO_ROOT / "backend" / "migrations" / "008_postgres_storage_v8.sql"
ALERT_DRILL = REPO_ROOT / "scripts" / "run_alert_delivery_drill.py"

SECURITY_HEADER_NAMES = (
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Content-Security-Policy",
)


def _active_text(path: Path) -> str:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        lines.append(raw)
    return "\n".join(lines)


def _yaml(path: Path) -> dict:
    assert path.is_file(), f"missing {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _prometheus_job(name: str) -> dict:
    config = _yaml(PROMETHEUS)
    for job in config.get("scrape_configs", []):
        if job.get("job_name") == name:
            return job
    msg = f"prometheus.yml missing scrape job {name!r}"
    raise AssertionError(msg)


def _alert_rule(alert_name: str) -> dict:
    config = _yaml(PROMETHEUS_ALERTS)
    for group in config.get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("alert") == alert_name:
                return rule
    msg = f"prometheus_alerts.yml missing alert {alert_name!r}"
    raise AssertionError(msg)


def _load_alert_drill_module():
    module_name = "run_alert_delivery_drill_test_mod"
    spec = importlib.util.spec_from_file_location(module_name, ALERT_DRILL)
    assert spec and spec.loader, f"could not import {ALERT_DRILL}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestNginxSecurityHeaderSource:
    """F-NGINX-004: header values must live in one included snippet."""

    def test_security_header_snippet_is_mounted_and_included(self) -> None:
        assert NGINX_SECURITY_HEADERS.is_file(), "nginx security headers must live in nginx/security_headers.conf"
        nginx = _active_text(NGINX_CONF)
        compose = _yaml(PROD_COMPOSE)
        nginx_volumes = compose["services"]["nginx"].get("volumes", [])

        assert "include /etc/nginx/security_headers.conf;" in nginx
        assert "./nginx/security_headers.conf:/etc/nginx/security_headers.conf:ro" in nginx_volumes

    def test_security_header_values_are_not_repeated_in_nginx_conf(self) -> None:
        nginx = _active_text(NGINX_CONF)
        snippet = _active_text(NGINX_SECURITY_HEADERS)

        for header in SECURITY_HEADER_NAMES:
            assert f"add_header {header} " not in nginx, (
                f"{header} is still set directly in nginx.conf; use the shared snippet to avoid drift"
            )
            assert snippet.count(f"add_header {header} ") == 1, (
                f"{header} must be defined exactly once in nginx/security_headers.conf"
            )


class TestPrometheusAlertingFoundation:
    """F-MON-003/F-MON-005/F-MON-006/F-MON-010 deployment guards."""

    def test_alertmanager_is_scraped_and_has_down_alert(self) -> None:
        job = _prometheus_job("alertmanager")
        targets = {target for static_config in job.get("static_configs", []) for target in static_config.get("targets", [])}
        rule = _alert_rule("DataForgeAlertmanagerDown")

        assert "alertmanager:9093" in targets
        assert 'up{job="alertmanager"} == 0' in str(rule.get("expr"))
        assert rule.get("labels", {}).get("severity") == "critical"

    def test_prometheus_self_scrape_relabels_instance(self) -> None:
        job = _prometheus_job("prometheus")
        relabels = job.get("relabel_configs", [])

        assert any(
            item.get("target_label") == "instance" and item.get("replacement") == "prometheus-self" for item in relabels
        ), "prometheus self-scrape must replace instance=prometheus:9090 with a unique self label"

    def test_empty_prometheus_web_auth_disables_lifecycle_endpoint(self) -> None:
        web = _yaml(PROMETHEUS_WEB)
        compose = _yaml(PROD_COMPOSE)
        command = "\n".join(compose["services"]["prometheus"].get("command", []))

        if not web.get("basic_auth_users"):
            assert "--web.enable-lifecycle" not in command, (
                "Prometheus lifecycle reload must not be enabled while prometheus_web.yml has no basic-auth users"
            )

    def test_metrics_token_failure_has_distinct_root_cause_alert(self) -> None:
        blackbox_job = _prometheus_job("blackbox-dataforge-ready")
        dataforge_rule = _alert_rule("DataForgeAPIInstanceDown")
        token_rule = _alert_rule("DataForgeMetricsScrapeFailed")

        assert "blackbox-exporter:9115" in str(blackbox_job)
        assert 'probe_success{job="blackbox-dataforge-ready"} == 0' in str(dataforge_rule.get("expr"))
        assert 'up{job="dataforge"} == 0' in str(token_rule.get("expr"))
        assert 'probe_success{job="blackbox-dataforge-ready"} == 1' in str(token_rule.get("expr"))


class TestAlertDeliveryDrillSlackChannel:
    """F-MON-008: staging drill can prove the Slack channel exists."""

    def test_parser_exposes_slack_channel_reachability_gate(self) -> None:
        mod = _load_alert_drill_module()
        args = mod.build_parser().parse_args(
            [
                "--channel-assert-reachable",
                "--slack-bot-token",
                "xoxb-test-token",
                "--slack-channel-id",
                "C0123456789",
            ]
        )

        assert args.channel_assert_reachable is True
        assert args.slack_bot_token == "xoxb-test-token"
        assert args.slack_channel_id == "C0123456789"

    def test_slack_channel_check_fails_closed_without_credentials(self) -> None:
        mod = _load_alert_drill_module()
        result = mod.validate_slack_channel_reachable("", "C0123456789", timeout_seconds=0.1)

        assert result.reachable is False
        assert result.reason == "missing_slack_channel_credentials"


def test_postgres_schema_version_tracking_is_current_checkout_reality() -> None:
    """F-DB-002 is stale in this checkout; lock the current schema-version path."""
    migrations = STORAGE_MIGRATIONS.read_text(encoding="utf-8")
    exported_sql = POSTGRES_MIGRATION.read_text(encoding="utf-8")

    assert "POSTGRES_SCHEMA_VERSION = 8" in migrations
    assert "CREATE TABLE IF NOT EXISTS schema_version" in migrations
    assert "SELECT MAX(version) AS version FROM schema_version" in migrations
    assert "INSERT INTO schema_version (version) VALUES (%s)" in migrations
    assert "CREATE TABLE IF NOT EXISTS public.schema_version" in exported_sql
    assert "INSERT INTO public.schema_version (version, comment)" in exported_sql
