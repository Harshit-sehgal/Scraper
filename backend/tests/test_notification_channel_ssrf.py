"""SSRF-defense tests for the notification channel create/update models.

A security audit found that ``NotificationChannelCreate.webhook_url`` and
``NotificationChannelUpdate.webhook_url`` were accepted raw — only
``max_length=2048`` — and the downstream Slack/Teams/Discord notifiers
posted via raw ``httpx.AsyncClient``. An authenticated admin/operator
could therefore register a notification channel with a ``webhook_url``
pointing at ``http://169.254.169.254`` (AWS IMDS), ``http://localhost:6379``,
or any internal service, and the next job-completion would trigger a
server-side POST — bypassing the SSRF safe-transport that every other
outbound-HTTP path uses.

These tests verify the Pydantic-model-level defense that was added to
close CRITICAL-1 and CRITICAL-2 of the SSRF audit, plus a runtime
check that the notifier delivery path delegates to
``get_safe_async_client`` (defense-in-depth: even if a URL slipped
through, the transport would refuse to dial a private IP).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.models.auth import NotificationChannelCreate, NotificationChannelUpdate
from pydantic import ValidationError

# Hosts the SSRF defense MUST reject.  Covers RFC1918, loopback, link-local,
# carrier-grade NAT, cloud metadata, IPv6 loopback, link-local IPv6,
# and an internal-looking DNS name.  ``localhost`` should resolve to
# 127.0.0.1 so it is rejected at host-resolve time even without a
# literal-IP check.
SSRF_TARGETS = [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/x",  # AWS/IMDS
    "http://localhost:6379/",  # redis
    "http://127.0.0.1:9000/",  # minio loopback
    "http://10.0.0.5/",  # private RFC1918
    "http://172.16.5.5/",  # private RFC1918 (172.16/12)
    "http://192.168.1.1/",  # private RFC1918 (router)
    "http://100.64.0.1/",  # CGNAT 100.64/10
    "http://[::1]/",  # IPv6 loopback
    "http://[fe80::1]/",  # IPv6 link-local
    "http://metadata.google.internal/",  # GCE metadata DNS
    "http://internal.svc.cluster.local/",  # k8s internal service DNS
    "gopher://example.com/",  # disallowed scheme
    "ftp://example.com/file",  # disallowed scheme
    "file:///etc/passwd",  # disallowed scheme
    "javascript:alert(1)",  # disallowed scheme
]


class TestNotificationChannelCreateRejectsSSRF:
    """NotificationChannelCreate.webhook_url MUST reject SSRF targets."""

    @pytest.mark.parametrize("url", SSRF_TARGETS)
    def test_create_rejects_ssrf_or_unsafe_scheme(self, url: str) -> None:
        with pytest.raises(ValidationError):
            NotificationChannelCreate(type="slack", webhook_url=url)

    def test_create_rejects_empty_webhook_url(self) -> None:
        """The ``...`` required-field default rejects missing; an empty
        string is rejected by the ``startswith`` scheme guard."""
        with pytest.raises(ValidationError):
            NotificationChannelCreate(type="slack", webhook_url="")

    def test_create_strips_whitespace_before_validation(self) -> None:
        """The validator strips the input before persisting — an
        attacker cannot sneak a private URL past the check by padding
        with leading/trailing whitespace that the startswith would
        otherwise miss on a non-stripped comparison."""
        with pytest.raises(ValidationError):
            NotificationChannelCreate(type="slack", webhook_url="  http://169.254.169.254/  ")

    def test_create_normalizes_valid_public_url(self) -> None:
        """A valid public HTTP(S) URL is accepted and stored stripped."""
        m = NotificationChannelCreate(type="slack", webhook_url="  https://hooks.slack.com/services/x/y/z  ")
        assert m.webhook_url == "https://hooks.slack.com/services/x/y/z"

    def test_create_accepts_public_ipv4(self) -> None:
        """Public-IP literals (not in RFC1918/loopback/etc.) pass — the
        rejection is by IP-class, not a blanket 'no IP literals'."""
        m = NotificationChannelCreate(type="slack", webhook_url="http://8.8.8.8/hook")
        assert m.webhook_url == "http://8.8.8.8/hook"


class TestNotificationChannelUpdateRejectsSSRF:
    """NotificationChannelUpdate.webhook_url MUST reject the same set —
    a PATCH path is otherwise a trivial way to swap a previously-valid
    Slack URL for a private IP after creation."""

    @pytest.mark.parametrize("url", SSRF_TARGETS)
    def test_update_rejects_ssrf_or_unsafe_scheme(self, url: str) -> None:
        with pytest.raises(ValidationError):
            NotificationChannelUpdate(webhook_url=url)

    def test_update_allows_unset_webhook_url(self) -> None:
        """An Update that omits webhook_url (None) MUST pass — callers
        use partial-update to flip ``enabled`` / ``events`` without
        touching the existing webhook URL."""
        m = NotificationChannelUpdate(enabled=False)
        assert m.webhook_url is None
        assert m.enabled is False

    def test_update_normalizes_valid_public_url(self) -> None:
        m = NotificationChannelUpdate(webhook_url="  http://example.com/hook  ")
        assert m.webhook_url == "http://example.com/hook"


class TestNotifierDeliveryUsesSafeTransport:
    """Defense-in-depth: the HTTP notifiers SHOULD call
    ``get_safe_async_client`` instead of raw ``httpx.AsyncClient``.
    If a bad URL somehow slipped through model validation (e.g. a
    legacy row in storage from before the validator shipped), the
    transport-layer IP check would still block the dial."""

    def test_slack_notifier_uses_safe_async_client(self) -> None:
        """SlackNotifier.send must construct via get_safe_async_client."""
        from app.services.notifications import SlackNotifier

        with patch("app.url_safety.get_safe_async_client") as mock_factory:
            mock_factory.return_value.post = lambda *a, **kw: None
            # We don't care about the result; we care that the factory
            # was invoked at all.  Raise mid-flight to short-circuit.
            mock_factory.side_effect = RuntimeError("factory-called")
            notifier = SlackNotifier()
            import asyncio

            with pytest.raises(RuntimeError, match="factory-called"):
                asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(
                        notifier.send("https://hooks.slack.com/x", "s", "b"),
                        timeout=2,
                    )
                )
            mock_factory.assert_called_once()

    def test_teams_notifier_uses_safe_async_client(self) -> None:
        from app.services.notifications import TeamsNotifier

        with patch("app.url_safety.get_safe_async_client") as mock_factory:
            mock_factory.side_effect = RuntimeError("factory-called")
            notifier = TeamsNotifier()
            import asyncio

            with pytest.raises(RuntimeError, match="factory-called"):
                asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(
                        notifier.send("https://outlook.office.com/webhook/x", "s", "b"),
                        timeout=2,
                    )
                )
            mock_factory.assert_called_once()

    def test_discord_notifier_uses_safe_async_client(self) -> None:
        from app.services.notifications import DiscordNotifier

        with patch("app.url_safety.get_safe_async_client") as mock_factory:
            mock_factory.side_effect = RuntimeError("factory-called")
            notifier = DiscordNotifier()
            import asyncio

            with pytest.raises(RuntimeError, match="factory-called"):
                asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(
                        notifier.send("https://discord.com/api/webhooks/x/y", "s", "b"),
                        timeout=2,
                    )
                )
            mock_factory.assert_called_once()
