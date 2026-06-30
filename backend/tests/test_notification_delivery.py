"""Tests for notification delivery — Slack, Teams, Discord, Email, and factory (Feat 35/36).

All HTTP and SMTP calls are mocked; no real network traffic is made.
"""

from __future__ import annotations

import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services.notifications import (
    _NOTIFIER_MAP,
    BaseNotifier,
    DiscordNotifier,
    EmailNotifier,
    SlackNotifier,
    TeamsNotifier,
    _resolve_timeout,
    deliver_notifications,
    get_notifier,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Factory tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetNotifier:
    """Verify the ``get_notifier`` factory returns the correct class."""

    def test_returns_slack_notifier(self) -> None:
        notifier = get_notifier("slack")
        assert isinstance(notifier, SlackNotifier)

    def test_returns_teams_notifier(self) -> None:
        notifier = get_notifier("teams")
        assert isinstance(notifier, TeamsNotifier)

    def test_returns_discord_notifier(self) -> None:
        notifier = get_notifier("discord")
        assert isinstance(notifier, DiscordNotifier)

    def test_returns_email_notifier(self) -> None:
        notifier = get_notifier("email")
        assert isinstance(notifier, EmailNotifier)

    def test_unknown_type_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown notification channel type"):
            get_notifier("pagerduty")

    def test_notifier_map_covers_all_types(self) -> None:
        assert set(_NOTIFIER_MAP.keys()) == {"slack", "teams", "discord", "email"}

    def test_all_notifiers_inherit_base(self) -> None:
        for cls in _NOTIFIER_MAP.values():
            assert issubclass(cls, BaseNotifier)


class TestResolveTimeout:
    """Verify ``_resolve_timeout`` returns a sensible float."""

    def test_returns_float(self) -> None:
        result = _resolve_timeout()
        assert isinstance(result, float)
        assert result > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Slack tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestSlackNotifier:
    async def test_send_success(self) -> None:
        """Verify Slack POST with valid webhook URL returns True."""
        notifier = SlackNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await notifier.send(
                "https://hooks.slack.com/services/T/B/xxx",
                "Job completed",
                "5 records extracted.",
            )
            assert result is True
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert "blocks" in payload
            assert payload["blocks"][0]["type"] == "header"

    async def test_send_includes_metadata_fields(self) -> None:
        """Verify metadata fields are appended to Slack blocks."""
        notifier = SlackNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await notifier.send(
                "https://hooks.slack.com/services/T/B/xxx",
                "Subject",
                "Body",
                metadata={"fields": [{"type": "mrkdwn", "text": "*Cost*: $0.01"}]},
            )
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert len(payload["blocks"]) == 3
            assert payload["blocks"][2]["type"] == "section"

    async def test_send_4xx_error_returns_false(self) -> None:
        """Verify Slack returns False on 4xx HTTP errors."""
        notifier = SlackNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=mock_resp,
            )
            result = await notifier.send(
                "https://hooks.slack.com/services/T/B/xxx",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_5xx_error_returns_false(self) -> None:
        """Verify Slack returns False on 5xx HTTP errors."""
        notifier = SlackNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=mock_resp,
            )
            result = await notifier.send(
                "https://hooks.slack.com/services/T/B/xxx",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_timeout_returns_false(self) -> None:
        """Verify Slack returns False on timeout."""
        notifier = SlackNotifier()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timed out")
            result = await notifier.send(
                "https://hooks.slack.com/services/T/B/xxx",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_connect_error_returns_false(self) -> None:
        """Verify Slack returns False on connection errors."""
        notifier = SlackNotifier()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            result = await notifier.send(
                "https://hooks.slack.com/services/T/B/xxx",
                "Subject",
                "Body",
            )
            assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Teams tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestTeamsNotifier:
    async def test_send_success(self) -> None:
        """Verify Teams POST with valid webhook URL returns True."""
        notifier = TeamsNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await notifier.send(
                "https://outlook.office.com/webhook/xxx",
                "Job completed",
                "5 records extracted.",
            )
            assert result is True
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert payload["type"] == "message"
            attachment = payload["attachments"][0]
            assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
            card = attachment["content"]
            assert card["type"] == "AdaptiveCard"

    async def test_send_adaptive_card_format(self) -> None:
        """Verify the AdaptiveCard body contains subject and text blocks."""
        notifier = TeamsNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await notifier.send(
                "https://outlook.office.com/webhook/xxx",
                "My Subject",
                "My Body",
            )
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            card_body = payload["attachments"][0]["content"]["body"]
            assert card_body[0]["text"] == "My Subject"
            assert card_body[0]["weight"] == "Bolder"
            assert card_body[1]["text"] == "My Body"

    async def test_send_includes_metadata_facts(self) -> None:
        """Verify metadata is rendered as a FactSet in the AdaptiveCard."""
        notifier = TeamsNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await notifier.send(
                "https://outlook.office.com/webhook/xxx",
                "Subject",
                "Body",
                metadata={"Job ID": "abc-123", "Status": "completed"},
            )
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            card_body = payload["attachments"][0]["content"]["body"]
            fact_set = card_body[-1]
            assert fact_set["type"] == "FactSet"
            assert len(fact_set["facts"]) == 2

    async def test_send_4xx_error_returns_false(self) -> None:
        """Verify Teams returns False on 4xx errors."""
        notifier = TeamsNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Forbidden",
                request=MagicMock(),
                response=mock_resp,
            )
            result = await notifier.send(
                "https://outlook.office.com/webhook/xxx",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_timeout_returns_false(self) -> None:
        """Verify Teams returns False on timeout."""
        notifier = TeamsNotifier()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timed out")
            result = await notifier.send(
                "https://outlook.office.com/webhook/xxx",
                "Subject",
                "Body",
            )
            assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Discord tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestDiscordNotifier:
    async def test_send_success(self) -> None:
        """Verify Discord POST with valid webhook URL returns True."""
        notifier = DiscordNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await notifier.send(
                "https://discord.com/api/webhooks/xxx/yyy",
                "Job completed",
                "5 records extracted.",
            )
            assert result is True
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            assert "embeds" in payload
            assert payload["embeds"][0]["title"] == "Job completed"

    async def test_send_rich_embed_format(self) -> None:
        """Verify Discord embed includes title and description."""
        notifier = DiscordNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await notifier.send(
                "https://discord.com/api/webhooks/xxx/yyy",
                "My Title",
                "My Description",
                metadata={"color": 16711680, "fields": [{"name": "Records", "value": "5"}]},
            )
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            embed = payload["embeds"][0]
            assert embed["title"] == "My Title"
            assert embed["description"] == "My Description"
            assert embed["color"] == 16711680
            assert embed["fields"][0]["name"] == "Records"

    async def test_send_rate_limit_429_returns_false(self) -> None:
        """Verify Discord returns False on rate limit (HTTP 429)."""
        notifier = DiscordNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "5"}
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Too Many Requests",
                request=MagicMock(),
                response=mock_resp,
            )
            result = await notifier.send(
                "https://discord.com/api/webhooks/xxx/yyy",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_5xx_error_returns_false(self) -> None:
        """Verify Discord returns False on server errors."""
        notifier = DiscordNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Service Unavailable",
                request=MagicMock(),
                response=mock_resp,
            )
            result = await notifier.send(
                "https://discord.com/api/webhooks/xxx/yyy",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_connect_error_returns_false(self) -> None:
        """Verify Discord returns False on connection errors."""
        notifier = DiscordNotifier()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            result = await notifier.send(
                "https://discord.com/api/webhooks/xxx/yyy",
                "Subject",
                "Body",
            )
            assert result is False

    async def test_send_no_metadata_leaves_defaults(self) -> None:
        """Verify Discord embed has no color or fields when metadata is absent."""
        notifier = DiscordNotifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aclose = AsyncMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await notifier.send(
                "https://discord.com/api/webhooks/xxx/yyy",
                "Title",
                "Desc",
            )
            payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
            embed = payload["embeds"][0]
            assert "color" not in embed
            assert "fields" not in embed


# ═══════════════════════════════════════════════════════════════════════════════
# Email tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestEmailNotifier:
    async def test_send_starttls_success(self) -> None:
        """Verify email is sent via STARTTLS when SMTP_USE_SSL is False."""
        notifier = EmailNotifier()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP", return_value=mock_smtp) as mock_smtp_cls,
        ):
            mock_settings.SMTP_HOST = "smtp.example.com"
            mock_settings.SMTP_PORT = 587
            mock_settings.SMTP_USER = "user"
            mock_settings.SMTP_PASS = "pass"
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = False
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send(
                "dest@example.com",
                "Job completed",
                "5 records extracted.",
            )
            assert result is True
            mock_smtp_cls.assert_called_once()
            mock_smtp.starttls.assert_called_once()
            mock_smtp.login.assert_called_once_with("user", "pass")
            mock_smtp.sendmail.assert_called_once()

    async def test_send_ssl_success(self) -> None:
        """Verify email is sent via implicit SSL when SMTP_USE_SSL is True."""
        notifier = EmailNotifier()
        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl.__enter__ = MagicMock(return_value=mock_smtp_ssl)
        mock_smtp_ssl.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP_SSL", return_value=mock_smtp_ssl) as mock_smtp_cls,
        ):
            mock_settings.SMTP_HOST = "smtp.example.com"
            mock_settings.SMTP_PORT = 465
            mock_settings.SMTP_USER = "user"
            mock_settings.SMTP_PASS = "pass"
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = True
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send(
                "dest@example.com",
                "Job completed",
                "5 records extracted.",
            )
            assert result is True
            mock_smtp_cls.assert_called_once()
            mock_smtp_ssl.login.assert_called_once_with("user", "pass")
            mock_smtp_ssl.sendmail.assert_called_once()

    async def test_send_no_smtp_host_returns_false(self) -> None:
        """Verify email returns False when SMTP_HOST is not configured."""
        notifier = EmailNotifier()

        with patch("app.services.notifications.settings") as mock_settings:
            mock_settings.SMTP_HOST = ""
            result = await notifier.send("dest@example.com", "Subject", "Body")
            assert result is False

    async def test_send_auth_failure_returns_false(self) -> None:
        """Verify email returns False on SMTP authentication failure."""
        notifier = EmailNotifier()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP", return_value=mock_smtp),
        ):
            mock_settings.SMTP_HOST = "smtp.example.com"
            mock_settings.SMTP_PORT = 587
            mock_settings.SMTP_USER = "user"
            mock_settings.SMTP_PASS = "wrong"
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = False
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send("dest@example.com", "Subject", "Body")
            assert result is False

    async def test_send_connect_error_returns_false(self) -> None:
        """Verify email returns False on SMTP connection failure."""
        notifier = EmailNotifier()

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, b"Cannot connect")),
        ):
            mock_settings.SMTP_HOST = "bad-host.example.com"
            mock_settings.SMTP_PORT = 587
            mock_settings.SMTP_USER = ""
            mock_settings.SMTP_PASS = ""
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = False
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send("dest@example.com", "Subject", "Body")
            assert result is False

    async def test_send_network_error_returns_false(self) -> None:
        """Verify email returns False on network/OSError."""
        notifier = EmailNotifier()

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP", side_effect=OSError("Network unreachable")),
        ):
            mock_settings.SMTP_HOST = "unreachable.example.com"
            mock_settings.SMTP_PORT = 587
            mock_settings.SMTP_USER = ""
            mock_settings.SMTP_PASS = ""
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = False
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send("dest@example.com", "Subject", "Body")
            assert result is False

    async def test_send_html_body_included(self) -> None:
        """Verify HTML body is attached when metadata.html_body is provided."""
        notifier = EmailNotifier()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP", return_value=mock_smtp),
        ):
            mock_settings.SMTP_HOST = "smtp.example.com"
            mock_settings.SMTP_PORT = 587
            mock_settings.SMTP_USER = ""
            mock_settings.SMTP_PASS = ""
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = False
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send(
                "dest@example.com",
                "Subject",
                "Plain body",
                metadata={"html_body": "<h1>HTML body</h1>"},
            )
            assert result is True
            # Verify the email message included both parts
            sendmail_args = mock_smtp.sendmail.call_args
            raw_msg = sendmail_args[0][2]
            assert "text/plain" in raw_msg
            assert "text/html" in raw_msg

    async def test_send_recipient_refused_returns_false(self) -> None:
        """Verify email returns False when the recipient is refused."""
        notifier = EmailNotifier()
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.sendmail.side_effect = smtplib.SMTPRecipientsRefused({"dest@example.com": (550, b"Rejected")})

        with (
            patch("app.services.notifications.settings") as mock_settings,
            patch("smtplib.SMTP", return_value=mock_smtp),
        ):
            mock_settings.SMTP_HOST = "smtp.example.com"
            mock_settings.SMTP_PORT = 587
            mock_settings.SMTP_USER = ""
            mock_settings.SMTP_PASS = ""
            mock_settings.SMTP_FROM = "no-reply@example.com"
            mock_settings.SMTP_USE_SSL = False
            mock_settings.NOTIFICATION_TIMEOUT_SECONDS = 10.0

            result = await notifier.send("dest@example.com", "Subject", "Body")
            assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Batch delivery tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestDeliverNotifications:
    async def test_deliver_to_matching_channels(self) -> None:
        """Verify deliver_notifications sends to channels matching the event."""
        channels = [
            {
                "id": "ch-1",
                "type": "slack",
                "webhook_url": "https://hooks.slack.com/xxx",
                "events": ["completed"],
                "enabled": True,
            },
            {
                "id": "ch-2",
                "type": "discord",
                "webhook_url": "https://discord.com/api/webhooks/xxx",
                "events": ["completed"],
                "enabled": True,
            },
        ]

        with (
            patch("app.routers.jobs_write._notification_channels_store", {"job-1": channels}),
            patch.object(SlackNotifier, "send", new_callable=AsyncMock, return_value=True),
            patch.object(DiscordNotifier, "send", new_callable=AsyncMock, return_value=True),
        ):
            results = await deliver_notifications("job-1", "completed", "Subject", "Body")
            assert results["ch-1"] is True
            assert results["ch-2"] is True

    async def test_skips_disabled_channels(self) -> None:
        """Verify disabled channels are not notified."""
        channels = [
            {
                "id": "ch-1",
                "type": "slack",
                "webhook_url": "https://hooks.slack.com/xxx",
                "events": ["completed"],
                "enabled": False,
            },
        ]

        with (
            patch("app.routers.jobs_write._notification_channels_store", {"job-1": channels}),
            patch.object(SlackNotifier, "send", new_callable=AsyncMock) as mock_send,
        ):
            results = await deliver_notifications("job-1", "completed", "Subject", "Body")
            assert "ch-1" not in results
            mock_send.assert_not_called()

    async def test_skips_channels_without_matching_event(self) -> None:
        """Verify channels that don't subscribe to the event are skipped."""
        channels = [
            {
                "id": "ch-1",
                "type": "slack",
                "webhook_url": "https://hooks.slack.com/xxx",
                "events": ["failed"],
                "enabled": True,
            },
        ]

        with (
            patch("app.routers.jobs_write._notification_channels_store", {"job-1": channels}),
            patch.object(SlackNotifier, "send", new_callable=AsyncMock) as mock_send,
        ):
            results = await deliver_notifications("job-1", "completed", "Subject", "Body")
            assert "ch-1" not in results
            mock_send.assert_not_called()

    async def test_unknown_channel_type_logged_and_false(self) -> None:
        """Verify unknown channel types are skipped with False result."""
        channels = [
            {
                "id": "ch-1",
                "type": "pagerduty",
                "webhook_url": "https://example.com/hook",
                "events": ["completed"],
                "enabled": True,
            },
        ]

        with patch("app.routers.jobs_write._notification_channels_store", {"job-1": channels}):
            results = await deliver_notifications("job-1", "completed", "Subject", "Body")
            assert results["ch-1"] is False

    async def test_no_channels_returns_empty(self) -> None:
        """Verify empty channel store results in empty dict."""
        with patch("app.routers.jobs_write._notification_channels_store", {}):
            results = await deliver_notifications("job-1", "completed", "Subject", "Body")
            assert results == {}

    async def test_send_failure_does_not_block_other_channels(self) -> None:
        """Verify a failing channel doesn't prevent others from being notified."""
        channels = [
            {
                "id": "ch-1",
                "type": "slack",
                "webhook_url": "https://hooks.slack.com/xxx",
                "events": ["completed"],
                "enabled": True,
            },
            {
                "id": "ch-2",
                "type": "discord",
                "webhook_url": "https://discord.com/api/webhooks/xxx",
                "events": ["completed"],
                "enabled": True,
            },
        ]

        async def _slack_fail(*args, **kwargs):
            _msg = "boom"
            raise RuntimeError(_msg)

        with (
            patch("app.routers.jobs_write._notification_channels_store", {"job-1": channels}),
            patch.object(SlackNotifier, "send", new_callable=AsyncMock, side_effect=_slack_fail),
            patch.object(DiscordNotifier, "send", new_callable=AsyncMock, return_value=True),
        ):
            results = await deliver_notifications("job-1", "completed", "Subject", "Body")
            assert results["ch-1"] is False
            assert results["ch-2"] is True
