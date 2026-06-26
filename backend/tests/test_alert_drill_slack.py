"""Tests for Slack webhook delivery in the alert delivery drill.

Verifies that ``send_slack_webhook`` posts a properly formatted payload
to the configured incoming webhook URL and classifies the result
correctly.

These tests import from ``scripts.run_alert_delivery_drill`` which sits
outside the ``app`` package, so we add the repo root to ``sys.path``.
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# The alert drill script lives at <repo_root>/scripts/ — add repo root
# so ``scripts.run_alert_delivery_drill`` resolves.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.run_alert_delivery_drill import (  # noqa: I001
    AlertDrillConfig,
    AlertDrillResult,
    SlackWebhookResult,
    build_result,
    send_slack_webhook,
    validate_slack_channel_reachable,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _base_config(**overrides) -> AlertDrillConfig:
    defaults = {
        "alertmanager_url": "http://localhost:9093",
        "alertname": "TestDrill",
        "severity": "info",
        "drill_id": "drill-test",
        "timeout_seconds": 5.0,
        "poll_interval_seconds": 1.0,
        "alert_duration_seconds": 60,
        "notification_evidence": "",
        "require_notification_evidence": False,
        "channel_assert_reachable": False,
        "slack_bot_token": "",
        "slack_channel_id": "",
        "slack_webhook_url": "",
        "slack_webhook_enabled": False,
        "extra_labels": {},
    }
    defaults.update(overrides)
    return AlertDrillConfig(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# send_slack_webhook — delivery logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestSendSlackWebhook:
    def test_empty_url_returns_no_webhook_url(self) -> None:
        result = send_slack_webhook("", "TestAlert", "info", "drill-1", "http://localhost:9093")
        assert result.delivered is False
        assert result.reason == "no_webhook_url"

    def test_non_slack_url_returns_invalid_prefix(self) -> None:
        result = send_slack_webhook("https://example.com/webhook", "TestAlert", "info", "drill-1", "http://localhost:9093")
        assert result.delivered is False
        assert "invalid_webhook_url_prefix" in result.reason

    @patch("scripts.run_alert_delivery_drill.http_request")
    def test_success_returns_delivered(self, mock_http: MagicMock) -> None:
        from scripts.run_alert_delivery_drill import HttpResult

        mock_http.return_value = HttpResult(status_code=200, body="ok")

        result = send_slack_webhook(
            "https://hooks.slack.com/services/T00/B00/xxx",
            "TestAlert",
            "warning",
            "drill-abc",
            "http://localhost:9093",
        )

        assert result.delivered is True
        assert result.status_code == 200
        assert result.reason == "ok"
        # Verify the POST was made with the expected payload
        mock_http.assert_called_once()
        call_kwargs = mock_http.call_args
        assert call_kwargs[0][0] == "POST"  # method
        assert "hooks.slack.com" in call_kwargs[0][1]  # URL
        # Payload should contain blocks
        payload_arg = call_kwargs[1].get("payload") or call_kwargs.kwargs.get("payload")
        assert payload_arg is not None
        assert "blocks" in payload_arg
        assert payload_arg["text"] == "DataForge Synthetic Alert: TestAlert"

    @patch("scripts.run_alert_delivery_drill.http_request")
    def test_http_500_returns_failed(self, mock_http: MagicMock) -> None:
        from scripts.run_alert_delivery_drill import HttpResult

        mock_http.return_value = HttpResult(status_code=500, body="server error")

        result = send_slack_webhook(
            "https://hooks.slack.com/services/T00/B00/xxx",
            "TestAlert",
            "critical",
            "drill-500",
            "http://localhost:9093",
        )

        assert result.delivered is False
        assert result.status_code == 500
        assert "slack_webhook_http_500" in result.reason

    @patch("scripts.run_alert_delivery_drill.http_request", side_effect=OSError("connection refused"))
    def test_oserror_returns_request_failed(self, _mock_http: MagicMock) -> None:
        result = send_slack_webhook(
            "https://hooks.slack.com/services/T00/B00/xxx",
            "TestAlert",
            "info",
            "drill-oserr",
            "http://localhost:9093",
        )

        assert result.delivered is False
        assert result.status_code is None
        assert "webhook_request_failed" in result.reason

    @patch("scripts.run_alert_delivery_drill.http_request", side_effect=urllib.error.URLError("timeout"))
    def test_urlerror_returns_request_failed(self, _mock_http: MagicMock) -> None:
        result = send_slack_webhook(
            "https://hooks.slack.com/services/T00/B00/xxx",
            "TestAlert",
            "info",
            "drill-urlerr",
            "http://localhost:9093",
        )

        assert result.delivered is False
        assert "webhook_request_failed" in result.reason

    @patch("scripts.run_alert_delivery_drill.http_request")
    def test_payload_includes_all_fields(self, mock_http: MagicMock) -> None:
        from scripts.run_alert_delivery_drill import HttpResult

        mock_http.return_value = HttpResult(status_code=200, body="ok")

        send_slack_webhook(
            "https://hooks.slack.com/services/T00/B00/xxx",
            "MyAlert",
            "critical",
            "drill-fields",
            "http://am:9093",
        )

        call_kwargs = mock_http.call_args
        payload = call_kwargs[1].get("payload") or call_kwargs.kwargs.get("payload")
        assert payload is not None
        blocks = payload.get("blocks", [])
        # First block should be header
        assert blocks[0]["type"] == "header"
        # Second block should be section with fields
        section_fields = blocks[1].get("fields", [])
        field_texts = [f["text"] for f in section_fields]
        assert any("critical" in t for t in field_texts)
        assert any("drill-fields" in t for t in field_texts)


# ═══════════════════════════════════════════════════════════════════════════════
# build_result — webhook integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildResultWithWebhook:
    def test_webhook_failure_causes_drill_fail(self) -> None:
        config = _base_config(slack_webhook_url="https://hooks.slack.com/services/T/B/X", slack_webhook_enabled=True)
        wh = SlackWebhookResult(False, 500, "slack_webhook_http_500")
        result = build_result(
            config,
            ready_status_code=200,
            post_status_code=202,
            alert_visible=True,
            slack_webhook=wh,
        )
        assert result.passed is False
        assert "slack_webhook_failed" in result.failure_reason

    def test_webhook_success_does_not_fail(self) -> None:
        config = _base_config(slack_webhook_url="https://hooks.slack.com/services/T/B/X", slack_webhook_enabled=True)
        wh = SlackWebhookResult(True, 200, "ok")
        result = build_result(
            config,
            ready_status_code=200,
            post_status_code=202,
            alert_visible=True,
            slack_webhook=wh,
        )
        assert result.passed is True
        assert result.failure_reason == ""

    def test_webhook_not_attempted_when_disabled(self) -> None:
        config = _base_config(slack_webhook_url="", slack_webhook_enabled=False)
        result = build_result(
            config,
            ready_status_code=200,
            post_status_code=202,
            alert_visible=True,
        )
        assert result.slack_webhook_attempted is False
        assert result.slack_webhook_delivered is False

    def test_default_webhook_result_is_not_attempted(self) -> None:
        config = _base_config()
        result = build_result(
            config,
            ready_status_code=200,
            post_status_code=202,
            alert_visible=True,
        )
        assert result.slack_webhook_attempted is False
        assert result.slack_webhook_reason == "not_attempted"

    def test_channel_check_takes_precedence_over_webhook(self) -> None:
        """Channel unreachable failure fires before webhook failure."""
        from scripts.run_alert_delivery_drill import SlackChannelCheckResult

        config = _base_config(
            channel_assert_reachable=True,
            slack_webhook_url="https://hooks.slack.com/services/T/B/X",
            slack_webhook_enabled=True,
        )
        ch = SlackChannelCheckResult(False, "missing_slack_channel_credentials")
        wh = SlackWebhookResult(False, 500, "slack_webhook_http_500")
        result = build_result(
            config,
            ready_status_code=200,
            post_status_code=202,
            alert_visible=True,
            slack_channel_check=ch,
            slack_webhook=wh,
        )
        assert result.passed is False
        assert "slack_channel_unreachable" in result.failure_reason


# ═══════════════════════════════════════════════════════════════════════════════
# AlertDrillResult — new webhook fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlertDrillResultWebhookFields:
    def test_result_has_webhook_fields(self) -> None:
        result = AlertDrillResult(
            generated_at="2026-01-01T00:00:00Z",
            alertmanager_url="http://localhost:9093",
            alertname="Test",
            severity="info",
            drill_id="d1",
            ready_status_code=200,
            post_status_code=202,
            alert_visible=True,
            notification_delivery_confirmed=False,
            notification_evidence="",
            require_notification_evidence=False,
            slack_channel_check_required=False,
            slack_channel_reachable=False,
            slack_channel_check_reason="not_required",
            slack_webhook_attempted=True,
            slack_webhook_delivered=True,
            slack_webhook_status_code=200,
            slack_webhook_reason="ok",
            passed=True,
            failure_reason="",
        )
        d = result.to_dict()
        assert d["slack_webhook_attempted"] is True
        assert d["slack_webhook_delivered"] is True
        assert d["slack_webhook_status_code"] == 200
        assert d["slack_webhook_reason"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# validate_slack_channel_reachable — no regression
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateSlackChannelReachable:
    def test_missing_credentials(self) -> None:
        result = validate_slack_channel_reachable("", "")
        assert result.reachable is False
        assert result.reason == "missing_slack_channel_credentials"

    def test_missing_token_only(self) -> None:
        result = validate_slack_channel_reachable("", "C123")
        assert result.reachable is False
        assert result.reason == "missing_slack_channel_credentials"

    def test_missing_channel_only(self) -> None:
        result = validate_slack_channel_reachable("xoxb-test", "")
        assert result.reachable is False
        assert result.reason == "missing_slack_channel_credentials"
