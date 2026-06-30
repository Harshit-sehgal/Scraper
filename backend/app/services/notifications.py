"""Notification delivery service — Slack, Teams, Discord, Email, and Telegram (Feat 35/36).

Each notifier implements the ``BaseNotifier`` interface with a single
``send(recipient, subject, body, metadata)`` async method that returns
``True`` on success and ``False`` on failure.  HTTP-based notifiers
use ``httpx.AsyncClient`` with configurable timeouts; the email
notifier uses stdlib ``smtplib`` + ``email.mime`` for SMTP delivery.

Channel routing is handled by ``get_notifier(channel_type)`` which
returns the correct notifier class for a given channel type string.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Default timeout for webhook notifiers ──────────────────────────────────

_DEFAULT_TIMEOUT: float = 10.0


def _resolve_timeout() -> float:
    """Return the notification timeout from settings, falling back to the module default."""
    try:
        return float(settings.NOTIFICATION_TIMEOUT_SECONDS)
    except (AttributeError, TypeError, ValueError):
        return _DEFAULT_TIMEOUT


# ─── Abstract base ────────────────────────────────────────────────────────────


class BaseNotifier(ABC):
    """Abstract base class for all notification channel notifiers."""

    @abstractmethod
    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: dict | None = None,
    ) -> bool:
        """Send a notification.

        Args:
            recipient: Channel-specific address (webhook URL, email address, etc.).
            subject: Notification subject line.
            body: Notification body text (plain text).
            metadata: Optional dict with extra channel-specific data.

        Returns:
            ``True`` if the notification was delivered, ``False`` otherwise.
        """


# ─── Slack ───────────────────────────────────────────────────────────────────


class SlackNotifier(BaseNotifier):
    """Sends notifications to Slack via Incoming Webhook with Block Kit formatting."""

    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: dict | None = None,
    ) -> bool:
        """Post a Slack message with formatted blocks to the webhook URL.

        Args:
            recipient: Slack Incoming Webhook URL.
            subject: Used as the message header text in the block.
            body: Plain-text body rendered as a section block.
            metadata: Optional extra fields merged into the Slack payload.
        """
        payload: dict = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": subject},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": body},
                },
            ],
        }
        if metadata:
            fields = metadata.get("fields")
            if fields and isinstance(fields, list):
                payload["blocks"].append(
                    {
                        "type": "section",
                        "fields": fields,
                    }
                )
        timeout = _resolve_timeout()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(recipient, json=payload)
                try:
                    resp.raise_for_status()
                finally:
                    await resp.aclose()
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Slack notification failed (HTTP %d): %s",
                exc.response.status_code,
                exc,
            )
            return False
        except httpx.TimeoutException:
            logger.warning("Slack notification timed out after %0.1fs", timeout)
            return False
        except httpx.ConnectError as exc:
            logger.warning("Slack notification connection error: %s", exc)
            return False


# ─── Microsoft Teams ─────────────────────────────────────────────────────────


class TeamsNotifier(BaseNotifier):
    """Sends notifications to Microsoft Teams via Workflows / Incoming Webhook
    using AdaptiveCard format."""

    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: dict | None = None,
    ) -> bool:
        """Post a Teams AdaptiveCard message to the webhook URL.

        Args:
            recipient: Microsoft Teams Incoming Webhook URL.
            subject: Used as the AdaptiveCard title text.
            body: Plain-text body rendered as a TextBlock.
            metadata: Optional extra fields merged into the payload.
        """
        facts: list[dict[str, str]] = []
        if metadata and isinstance(metadata, dict):
            for key, value in metadata.items():
                if key != "fields":
                    facts.append({"title": str(key), "value": str(value)})
        card_body: list[dict] = [
            {
                "type": "TextBlock",
                "text": subject,
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": body,
                "wrap": True,
            },
        ]
        if facts:
            card_body.append(
                {
                    "type": "FactSet",
                    "facts": facts,
                }
            )
        payload: dict = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": card_body,
                    },
                }
            ],
        }
        timeout = _resolve_timeout()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(recipient, json=payload)
                try:
                    resp.raise_for_status()
                finally:
                    await resp.aclose()
            return True
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Teams notification failed (HTTP %d): %s",
                exc.response.status_code,
                exc,
            )
            return False
        except httpx.TimeoutException:
            logger.warning("Teams notification timed out after %0.1fs", timeout)
            return False
        except httpx.ConnectError as exc:
            logger.warning("Teams notification connection error: %s", exc)
            return False


# ─── Discord ─────────────────────────────────────────────────────────────────


class DiscordNotifier(BaseNotifier):
    """Sends notifications to Discord via Webhook with rich embed formatting."""

    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: dict | None = None,
    ) -> bool:
        """Post a Discord message with a rich embed to the webhook URL.

        Args:
            recipient: Discord Webhook URL.
            subject: Used as the embed title.
            body: Plain-text body rendered as the embed description.
            metadata: Optional extra data; ``color`` (int) and ``fields`` (list) are honoured.
        """
        embed: dict = {
            "title": subject,
            "description": body,
        }
        if metadata:
            color = metadata.get("color")
            if isinstance(color, int):
                embed["color"] = color
            fields = metadata.get("fields")
            if isinstance(fields, list):
                embed["fields"] = fields
        payload: dict = {"embeds": [embed]}
        timeout = _resolve_timeout()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(recipient, json=payload)
                try:
                    resp.raise_for_status()
                finally:
                    await resp.aclose()
            return True
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # Discord returns 429 on rate limits; log at warning rather than error.
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After")
                logger.warning(
                    "Discord notification rate-limited (429), Retry-After: %s",
                    retry_after,
                )
            else:
                logger.warning(
                    "Discord notification failed (HTTP %d): %s",
                    status,
                    exc,
                )
            return False
        except httpx.TimeoutException:
            logger.warning("Discord notification timed out after %0.1fs", timeout)
            return False
        except httpx.ConnectError as exc:
            logger.warning("Discord notification connection error: %s", exc)
            return False


# ─── Email (SMTP) ────────────────────────────────────────────────────────────


class EmailNotifier(BaseNotifier):
    """Sends notification emails via SMTP (stdlib smtplib + email.mime).

    Supports both implicit SSL (port 465) and STARTTLS (port 587).
    Sends both plain-text and HTML body parts.
    """

    async def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        metadata: dict | None = None,
    ) -> bool:
        """Send an email via SMTP.

        Args:
            recipient: Destination email address.
            subject: Email subject line.
            body: Plain-text body; also used as fallback for HTML part.
            metadata: Optional dict; ``html_body`` key provides an HTML alternative.
        """
        smtp_host = settings.SMTP_HOST
        smtp_port = settings.SMTP_PORT
        smtp_user = settings.SMTP_USER
        smtp_pass = settings.SMTP_PASS
        smtp_from = settings.SMTP_FROM or "noreply@dataforge.local"

        if not smtp_host:
            logger.warning("Email notification skipped: SMTP_HOST not configured")
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = smtp_from
        msg["To"] = recipient
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain", "utf-8"))

        html_body: str | None = None
        if metadata and isinstance(metadata, dict):
            html_body = metadata.get("html_body")
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            if settings.SMTP_USE_SSL:
                # Implicit SSL (typically port 465)
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=_resolve_timeout()) as server:
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_from, [recipient], msg.as_string())
            else:
                # STARTTLS (typically port 587)
                with smtplib.SMTP(smtp_host, smtp_port, timeout=_resolve_timeout()) as server:
                    server.ehlo()
                    ctx = ssl.create_default_context()
                    server.starttls(context=ctx)
                    server.ehlo()
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_from, [recipient], msg.as_string())
            return True
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("Email notification SMTP auth failed: %s", exc)
            return False
        except smtplib.SMTPConnectError as exc:
            logger.warning("Email notification SMTP connect error: %s", exc)
            return False
        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning("Email notification recipient refused: %s", exc)
            return False
        except smtplib.SMTPException as exc:
            logger.warning("Email notification SMTP error: %s", exc)
            return False
        except OSError as exc:
            logger.warning("Email notification network error: %s", exc)
            return False


# ─── Notifier factory ────────────────────────────────────────────────────────

_NOTIFIER_MAP: dict[str, type[BaseNotifier]] = {
    "slack": SlackNotifier,
    "teams": TeamsNotifier,
    "discord": DiscordNotifier,
    "email": EmailNotifier,
}


def get_notifier(channel_type: str) -> BaseNotifier:
    """Return the appropriate notifier instance for *channel_type*.

    Raises:
        ValueError: If *channel_type* is not a known notifier type.
    """
    cls = _NOTIFIER_MAP.get(channel_type)
    if cls is None:
        msg = f"Unknown notification channel type: {channel_type!r}"
        raise ValueError(msg)
    return cls()


# ─── TelegramNotifier (legacy — retained for backward compatibility) ─────────


class TelegramNotifier:
    """Handles sending notifications via the Telegram Bot API."""

    def __init__(self) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.enabled = settings.TELEGRAM_ENABLED
        self._client: httpx.AsyncClient | None = None
        # L1: protect lazy client init from races when multiple coroutines
        # call _get_client() concurrently — without a guard two callers
        # can both observe None, both build a client, and leak the loser.
        self._client_lock = threading.Lock()

    def _get_client(self) -> httpx.AsyncClient:
        # Fast-path: client already alive — no lock needed for the common
        # case where the singleton was initialised on a prior call.
        client = self._client
        if client is not None and not client.is_closed:
            return client
        with self._client_lock:
            # Re-check under lock so only the first racer builds a client.
            client = self._client
            if client is None or client.is_closed:
                from app.url_safety import get_safe_async_client

                client = get_safe_async_client(timeout=30.0)
                self._client = client
            return client

    async def send_message(self, text: str) -> None:
        """Send a simple text message to the connected chat."""
        if not self.enabled or not self.token or not self.chat_id:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}

        try:
            client = self._get_client()
            response = await client.post(url, json=payload)
            try:
                response.raise_for_status()
            finally:
                # H5: always release the response back to the pool
                # before the function exits — the previous pattern let
                # undetermined responses pile up under failure paths.
                await response.aclose()
        except Exception:
            logger.exception("Failed to send Telegram notification")

    async def close(self) -> None:
        """Close the underlying HTTP client to release sockets."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


notifier = TelegramNotifier()


def get_telegram_notifier() -> TelegramNotifier:
    """Return the module-level singleton notifier."""
    return notifier


# ─── Batch notification delivery ─────────────────────────────────────────────


async def deliver_notifications(
    job_id: str,
    event: str,
    subject: str,
    body: str,
    metadata: dict | None = None,
) -> dict[str, bool]:
    """Deliver notifications to all configured channels for a job.

    Reads the notification channel store from ``jobs_write`` and fires
    a notification for each enabled channel whose ``events`` list includes
    *event*.  Returns a mapping of ``channel_id -> delivered (bool)``.

    This is a best-effort operation — individual channel failures are
    logged but never prevent other channels from being notified.
    """
    from app.routers.jobs_write import _notification_channels_store

    channels = _notification_channels_store.get(job_id, [])
    results: dict[str, bool] = {}
    for ch in channels:
        if not ch.get("enabled", True):
            continue
        ch_events = ch.get("events", ["completed"])
        if event not in ch_events:
            continue
        ch_type = ch.get("type", "")
        ch_id = ch.get("id", "")
        recipient = ch.get("webhook_url", "")
        try:
            notifier_instance = get_notifier(ch_type)
        except ValueError:
            logger.warning("Skipping unknown channel type %r for job %s", ch_type, job_id)
            results[ch_id] = False
            continue
        try:
            success = await notifier_instance.send(recipient, subject, body, metadata)
            results[ch_id] = success
        except Exception:
            logger.exception(
                "Notification delivery threw unexpected error for channel %s (job %s)",
                ch_id,
                job_id,
            )
            results[ch_id] = False
    return results
