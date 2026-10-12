from __future__ import annotations  # noqa: I001

from argparse import ArgumentTypeError
from datetime import UTC, datetime
from pathlib import Path
import sys
import urllib.error
from unittest.mock import patch

import pytest

# The alert drill script lives at <repo_root>/scripts/ — add repo root
# so ``scripts.run_alert_delivery_drill`` resolves.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# must follow sys.path insertion above
from scripts.run_alert_delivery_drill import (
    AlertDrillConfig,
    alert_matches,
    build_alert_payload,
    build_result,
    display_url,
    endpoint,
    http_request,
    normalize_base_url,
    parse_alerts,
    parse_label,
)


def _config(
    *,
    notification_evidence: str = "",
    require_notification_evidence: bool = False,
) -> AlertDrillConfig:
    return AlertDrillConfig(
        alertmanager_url="http://localhost:9093",
        alertname="DataForgeSyntheticAlertDrill",
        severity="info",
        drill_id="unit-drill",
        timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        alert_duration_seconds=300,
        notification_evidence=notification_evidence,
        require_notification_evidence=require_notification_evidence,
        channel_assert_reachable=False,
        slack_bot_token="",
        slack_channel_id="",
        slack_webhook_url="",
        slack_webhook_enabled=False,
        extra_labels={"environment": "test"},
    )


def test_url_helpers_normalize_and_redact_credentials():
    assert normalize_base_url("http://user:secret@example.com:9093/base/?token=abc") == "http://user:secret@example.com:9093/base"
    assert display_url("http://user:secret@example.com:9093/base?token=abc") == "http://example.com:9093/base"
    assert endpoint("http://localhost:9093/", "/api/v2/alerts") == "http://localhost:9093/api/v2/alerts"

    with pytest.raises(ArgumentTypeError):
        normalize_base_url("localhost:9093")


def test_http_request_returns_structured_failure_on_connection_error():
    with patch(
        "scripts.run_alert_delivery_drill.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        result = http_request("GET", "http://127.0.0.1:1/-/ready", timeout_seconds=0.1)

    assert result.status_code == 0
    assert result.body.startswith("URLError:")


def test_parse_label_requires_key_value_format():
    assert parse_label("environment=staging") == ("environment", "staging")

    with pytest.raises(ArgumentTypeError):
        parse_label("environment")


def test_build_alert_payload_includes_drill_labels_and_times():
    payload = build_alert_payload(_config(), starts_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC))

    assert len(payload) == 1
    alert = payload[0]
    assert alert["labels"]["alertname"] == "DataForgeSyntheticAlertDrill"
    assert alert["labels"]["drill_id"] == "unit-drill"
    assert alert["labels"]["environment"] == "test"
    assert alert["startsAt"] == "2026-06-24T09:00:00Z"
    assert alert["endsAt"] == "2026-06-24T09:05:00Z"
    assert "Slack/email delivery" in alert["annotations"]["description"]


def test_parse_alerts_and_match_by_alertname_and_drill_id():
    raw = '[{"labels":{"alertname":"DataForgeSyntheticAlertDrill","drill_id":"unit-drill"}},{"labels":{"alertname":"Other"}}]'
    alerts = parse_alerts(raw)

    assert any(alert_matches(alert, _config()) for alert in alerts)
    assert not alert_matches({"labels": {"alertname": "DataForgeSyntheticAlertDrill", "drill_id": "other"}}, _config())
    assert parse_alerts('{"not":"a-list"}') == []


def test_build_result_requires_notification_evidence_only_when_configured():
    result = build_result(
        _config(),
        ready_status_code=200,
        post_status_code=200,
        alert_visible=True,
        generated_at=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
    )

    assert result.passed is True
    assert result.notification_delivery_confirmed is False
    assert result.generated_at == "2026-06-24T09:00:00Z"

    required = build_result(
        _config(require_notification_evidence=True),
        ready_status_code=200,
        post_status_code=200,
        alert_visible=True,
    )
    assert required.passed is False
    assert required.failure_reason == "notification_evidence_required"

    confirmed = build_result(
        _config(notification_evidence="Slack thread https://example.invalid/thread", require_notification_evidence=True),
        ready_status_code=200,
        post_status_code=200,
        alert_visible=True,
    )
    assert confirmed.passed is True
    assert confirmed.notification_delivery_confirmed is True
