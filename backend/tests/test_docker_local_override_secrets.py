"""Regression guards for local production-stack override secrets."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_OVERRIDE = REPO_ROOT / "docker-compose.override.local.yml"


def _override_text() -> str:
    assert LOCAL_OVERRIDE.is_file(), f"missing {LOCAL_OVERRIDE}"
    return LOCAL_OVERRIDE.read_text(encoding="utf-8")


def test_local_override_has_no_literal_postgres_password_in_dsn() -> None:
    text = _override_text()
    literal_dsn = re.search(r"postgres(?:ql)?://[^\s:$]+:[^\s${}@]+@", text)
    assert not literal_dsn, (
        "docker-compose.override.local.yml contains a literal Postgres password "
        "inside a DSN; use ${DATAFORGE_DB_PASSWORD:?...} substitution"
    )
    assert "${DATAFORGE_DB_PASSWORD:?" in text


def test_local_override_has_no_literal_grafana_admin_password() -> None:
    text = _override_text()
    literal_password = re.search(
        r"GF_SECURITY_ADMIN_PASSWORD=(?!\$\{)[^\s]+",
        text,
    )
    assert not literal_password, (
        "docker-compose.override.local.yml hardcodes GF_SECURITY_ADMIN_PASSWORD; use ${GRAFANA_PASSWORD:?...} substitution"
    )
    assert "${GRAFANA_PASSWORD:?" in text


def test_local_override_has_no_committed_slack_webhook_url() -> None:
    text = _override_text()
    assert "hooks.slack.com" not in text
    assert "${ALERTMANAGER_SLACK_WEBHOOK_URL:?" in text
