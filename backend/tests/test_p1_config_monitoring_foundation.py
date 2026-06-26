"""Regression guards for P1 config/docs/monitoring foundation issues."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
MAKEFILE = REPO_ROOT / "Makefile"
DEV_ENV = REPO_ROOT / ".env.example"
PROD_ENV = REPO_ROOT / ".env.production.example"
CHECK_PROD_ENV = REPO_ROOT / "scripts" / "check_prod_env.py"
ALERTMANAGER = REPO_ROOT / "alertmanager.yml"
PROMETHEUS_ALERTS = REPO_ROOT / "prometheus_alerts.yml"


def _load_check_prod_env_module():
    spec = importlib.util.spec_from_file_location("check_prod_env_p1", CHECK_PROD_ENV)
    assert spec and spec.loader, f"could not import {CHECK_PROD_ENV}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            stripped = stripped[1:].strip()
        if not stripped or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


@pytest.fixture
def reset_metrics():
    from app.metrics_collector import reset_for_testing

    reset_for_testing()
    yield
    reset_for_testing()


def test_readme_states_make_validate_runs_full_gate() -> None:
    """F-DOC-001: README and Makefile must agree on validate semantics."""
    makefile = MAKEFILE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert re.search(
        r"^validate:.*\n\tpython3 scripts/validate_local\.py --full",
        makefile,
        flags=re.MULTILINE,
    ), "Makefile validate target must continue to run the full validation gate"
    assert "make validate` runs `python3 scripts/validate_local.py --full" in readme, (
        "README.md must explicitly say that make validate runs the full gate; otherwise operators "
        "expect the quick local smoke gate and get a slower full run."
    )


def test_production_template_documents_all_telegram_notification_vars() -> None:
    """F-ENV-002: production env template must not omit notification vars."""
    dev_telegram = {key for key in _env_keys(DEV_ENV) if key.startswith("DATAFORGE_TELEGRAM_")}
    prod_telegram = {key for key in _env_keys(PROD_ENV) if key.startswith("DATAFORGE_TELEGRAM_")}

    assert dev_telegram, "dev env template should document DATAFORGE_TELEGRAM_* notification vars"
    assert dev_telegram <= prod_telegram, (
        f".env.production.example omits notification variables that exist in .env.example: {sorted(dev_telegram - prod_telegram)}"
    )


def test_check_prod_env_requires_and_validates_grafana_user() -> None:
    """F-ENV-003: non-admin Grafana user drift must fail the prod gate."""
    mod = _load_check_prod_env_module()

    assert "GRAFANA_USER" in mod.REQUIRED_VARS
    assert "GRAFANA_PASSWORD" in mod.REQUIRED_VARS
    assert not mod.check_grafana_user("ops")
    assert not mod.check_grafana_user("")
    assert mod.check_grafana_user("admin")


def test_check_prod_env_requires_llm_provider_when_public_fallbacks_disabled() -> None:
    """F-ENV-005: fully functional AI extraction needs an explicit LLM key."""
    mod = _load_check_prod_env_module()

    missing_key_env = {"DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS": "false"}
    prefixed_key_env = {
        "DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS": "false",
        "DATAFORGE_GROQ_API_KEY": "gsk_live_strong_key_value_123456",
    }
    legacy_key_env = {
        "DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS": "false",
        "GROQ_API_KEY": "gsk_live_strong_key_value_123456",
    }

    assert not mod.check_llm_provider_credentials(missing_key_env)
    assert mod.check_llm_provider_credentials(prefixed_key_env)
    assert mod.check_llm_provider_credentials(legacy_key_env)


def test_critical_alert_route_does_not_continue_to_default_receiver() -> None:
    """F-MON-007: critical alerts should not duplicate into default receiver."""
    config = yaml.safe_load(ALERTMANAGER.read_text(encoding="utf-8"))
    critical_routes = [route for route in config["route"]["routes"] if route.get("match", {}).get("severity") == "critical"]

    assert len(critical_routes) == 1
    critical_route = critical_routes[0]
    assert critical_route["receiver"] == "critical"
    assert critical_route.get("continue") is not True, (
        "critical alerts route to the critical receiver; continue: true duplicates the alert "
        "into the default receiver and doubles email volume."
    )


def test_repo_query_latency_alert_uses_exported_quantile_metric(client, reset_metrics) -> None:
    """F-MON-009: alert expression must target a metric actually exported by /metrics."""
    from app.metrics_collector import record_repo_query_latency

    for sample in (0.01, 0.02, 0.75, 0.9):
        record_repo_query_latency(sample)

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert 'dataforge_repo_query_latency_seconds{quantile="0.95"}' in metrics.text

    alerts = PROMETHEUS_ALERTS.read_text(encoding="utf-8")
    assert 'dataforge_repo_query_latency_seconds{quantile="0.95"} > 0.5' in alerts
