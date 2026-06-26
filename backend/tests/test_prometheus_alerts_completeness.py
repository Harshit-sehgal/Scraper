"""Regression guard for F-MON-004 — critical infrastructure alerts exist.

Pre-fix, the alert rules covered app-level signals only. No rules existed
for: Postgres disk utilization, container OOM kills, TLS certificate
expiry, Alertmanager liveness, node-exporter health, cadvisor health,
host filesystem space, or public HTTPS availability.

The fix adds real alerts for each gap. The node-exporter and cadvisor
services are deployed in docker-compose.prod.yml; the blackbox-exporter
gains a tls_connect module; and prometheus.yml adds scrape jobs for
node-exporter, cadvisor, and the TLS probe.

Assertions:

1. The YAML file parses without error.
2. All required alert names are present.
3. Each alert has a ``severity`` label.
4. Each alert has ``summary`` and ``description`` annotations.
5. Placeholder alerts have been replaced with real expressions (no
   ``absent(...)`` patterns that fire due to missing exporters).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ALERTS = REPO_ROOT / "prometheus_alerts.yml"
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
PROM = REPO_ROOT / "prometheus.yml"

# Alerts that F-MON-004 requires. The original 3 placeholder alerts
# (16, 17, 18) are now production rules with proper expressions.
# Alerts 19-22 cover node-exporter, cadvisor, host filesystem, and
# public HTTPS probing.
REQUIRED_ALERT_NAMES = (
    "DataForgeAPIInstanceDown",
    "DataForgeMetricsScrapeFailed",
    "DataForgeAlertmanagerDown",
    # F-MON-004 real alerts (previously placeholders)
    "PostgresDiskUsageHigh",
    "ContainerOOMKillPending",
    "TLSCertificateExpiring",
    # F-MON-004 new alerts
    "NodeExporterDown",
    "CadvisorDown",
    "NodeFilesystemSpaceFillingUp",
    "PublicHTTPSProbeFailing",
)

# Scrape jobs that F-MON-004 requires in prometheus.yml
REQUIRED_SCRAPE_JOBS = (
    "node-exporter",
    "cadvisor",
    "blackbox-tls",
)


def _load_alerts() -> list[dict]:
    assert ALERTS.is_file(), f"missing {ALERTS}"
    data = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    groups = data.get("groups", [])
    rules: list[dict] = []
    for group in groups:
        rules.extend(group.get("rules", []))
    return rules


def _load_prom() -> dict:
    assert PROM.is_file(), f"missing {PROM}"
    return yaml.safe_load(PROM.read_text(encoding="utf-8"))


def _load_compose() -> dict:
    assert COMPOSE.is_file(), f"missing {COMPOSE}"
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


class TestPrometheusAlertsCompleteness:
    """F-MON-004: critical infrastructure alerts are present."""

    def test_alerts_yaml_parses(self) -> None:
        _load_alerts()  # must not raise

    def test_required_alerts_present(self) -> None:
        rules = _load_alerts()
        alert_names = {r.get("alert", "") for r in rules}
        missing = set(REQUIRED_ALERT_NAMES) - alert_names
        assert not missing, f"F-MON-004: the following required alert names are missing from {ALERTS.name}: {sorted(missing)}"

    def test_each_alert_has_severity_label(self) -> None:
        rules = _load_alerts()
        for r in rules:
            alert = r.get("alert", "<unnamed>")
            labels = r.get("labels", {})
            assert "severity" in labels, (
                f"F-MON-004: alert '{alert}' is missing the ``severity`` label — operators cannot route it without one."
            )

    def test_each_alert_has_summary_and_description(self) -> None:
        rules = _load_alerts()
        for r in rules:
            alert = r.get("alert", "<unnamed>")
            annotations = r.get("annotations", {})
            assert "summary" in annotations, f"F-MON-004: alert '{alert}' is missing the ``summary`` annotation."
            assert "description" in annotations, f"F-MON-004: alert '{alert}' is missing the ``description`` annotation."

    def test_no_placeholder_alert_expressions(self) -> None:
        """Placeholder alerts used ``absent(...)`` as a signal that the
        exporter was not deployed. Now that exporters are deployed, all
        F-MON-004 alerts must use real metric expressions — no
        ``absent(...)`` patterns allowed."""
        rules = _load_alerts()
        for r in rules:
            alert = r.get("alert", "<unnamed>")
            expr = r.get("expr", "")
            if isinstance(expr, str):
                assert "absent(" not in expr, (
                    f"F-MON-004: alert '{alert}' still uses the placeholder ``absent(...)`` "
                    f"expression — replace with a real metric expression now that the "
                    f"corresponding exporter is deployed."
                )

    def test_infra_alerts_have_real_severity(self) -> None:
        """The original placeholder alerts had ``severity: info`` because
        they were just liveness probes for missing exporters. Now that
        the alerts fire on real conditions, they must have meaningful
        severity levels (warning or critical, not info)."""
        rules = _load_alerts()
        infra_alerts = {
            "PostgresDiskUsageHigh",
            "ContainerOOMKillPending",
            "TLSCertificateExpiring",
        }
        for r in rules:
            alert = r.get("alert", "")
            if alert in infra_alerts:
                severity = r.get("labels", {}).get("severity", "")
                assert severity in ("warning", "critical"), (
                    f"F-MON-004: alert '{alert}' has severity '{severity}' — infra alerts must be warning or critical, not info."
                )


class TestFMON004ScrapeJobs:
    """F-MON-004: required Prometheus scrape jobs are configured."""

    def test_required_scrape_jobs_present(self) -> None:
        prom = _load_prom()
        jobs = [sc.get("job_name", "") for sc in prom.get("scrape_configs", [])]
        missing = set(REQUIRED_SCRAPE_JOBS) - set(jobs)
        assert not missing, f"F-MON-004: missing scrape jobs in prometheus.yml: {sorted(missing)}"

    def test_blackbox_tls_probe_uses_tls_connect_module(self) -> None:
        prom = _load_prom()
        for sc in prom.get("scrape_configs", []):
            if sc.get("job_name") == "blackbox-tls":
                params = sc.get("params", {})
                assert "tls_connect" in params.get("module", []), (
                    "F-MON-004: blackbox-tls scrape job must use the tls_connect module"
                )
                break
        else:
            msg = "F-MON-004: blackbox-tls scrape job not found"
            raise AssertionError(msg)


class TestFMON004ComposeServices:
    """F-MON-004: node-exporter and cadvisor are defined in prod compose."""

    def test_node_exporter_service_present(self) -> None:
        compose = _load_compose()
        assert "node-exporter" in compose.get("services", {}), (
            "F-MON-004: node-exporter service missing from docker-compose.prod.yml"
        )

    def test_cadvisor_service_present(self) -> None:
        compose = _load_compose()
        assert "cadvisor" in compose.get("services", {}), "F-MON-004: cadvisor service missing from docker-compose.prod.yml"

    def test_node_exporter_image_is_pinned(self) -> None:
        compose = _load_compose()
        image = compose["services"]["node-exporter"].get("image", "")
        # Must contain a version tag (not :latest)
        assert ":" in image and "latest" not in image, f"F-MON-004: node-exporter image must be pinned, got: {image}"

    def test_cadvisor_image_is_pinned(self) -> None:
        compose = _load_compose()
        image = compose["services"]["cadvisor"].get("image", "")
        assert ":" in image and "latest" not in image, f"F-MON-004: cadvisor image must be pinned, got: {image}"
