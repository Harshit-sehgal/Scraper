"""Regression guard for F-MON-004 — critical infrastructure alerts exist.

Pre-fix, the alert rules covered app-level signals only. No rules existed
for: Postgres disk utilization, container OOM kills, TLS certificate
expiry, Alertmanager liveness, or node-exporter health.

The fix adds alerts for each gap. Where the supporting exporter is not
yet deployed, a *placeholder* alert with ``severity: info`` documents the
gap and the production-ready expression that should replace it once the
exporter is wired. This ensures the gap is surfaced rather than silently
missing.

Assertions:

1. The YAML file parses without error.
2. All required alert names are present.
3. Each alert has a ``severity`` label.
4. Each alert has ``summary`` and ``description`` annotations.
5. The ``DataForgeAlertmanagerDown`` alert exists (the original F-MON-004 gap).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ALERTS = REPO_ROOT / "prometheus_alerts.yml"

# Alerts that F-MON-004 requires. The placeholder alerts (16, 17, 18)
# are included even though they depend on exporters not yet deployed —
# they surface the gap rather than hiding it.
REQUIRED_ALERT_NAMES = (
    "DataForgeAPIInstanceDown",
    "DataForgeMetricsScrapeFailed",
    "DataForgeAlertmanagerDown",
    # F-MON-004 new alerts
    "PostgresDiskUsageHigh",
    "ContainerOOMKillPending",
    "TLSCertificateExpiring",
)


def _load_alerts() -> list[dict]:
    assert ALERTS.is_file(), f"missing {ALERTS}"
    data = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    groups = data.get("groups", [])
    rules: list[dict] = []
    for group in groups:
        rules.extend(group.get("rules", []))
    return rules


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
