"""
Domain Runtime Policy — per-domain concurrency, cooldown, and failure tracking.

When recovery handlers set ``reduce_concurrency`` or ``abort_domain``, this
module translates those signals into actionable runtime policy that affects
future fetch scheduling.

Governance constraints
----------------------
- Recovery must NEVER become a stealth/evasion bypass.  When a domain is in
  cooldown or has high anti-bot risk, the recommended action should always
  be truthful: ``"use_authorized_access_or_retry_later"``, not a silent retry.
- Rate-limited / anti-bot-blocked domains get cooldown + truthful recommended
  action surfaced through acquisition lineage.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default max parallel requests per domain.
_DEFAULT_MAX_PARALLEL: int = 2
# Seconds a domain stays in cooldown after hitting the failure limit.
_DEFAULT_COOLDOWN_SECONDS: int = 60
# Consecutive failures before a domain enters cooldown.
_COOLDOWN_FAILURE_LIMIT: int = 3


@dataclass
class DomainPolicyEntry:
    """Runtime policy for a single domain."""

    domain: str
    max_parallel: int = _DEFAULT_MAX_PARALLEL
    """Maximum number of concurrent fetches allowed for this domain."""

    cooldown_until: float = 0.0
    """Monotonic time before which this domain should not be fetched."""

    recent_failures: int = 0
    """Consecutive recent failures (reset on success)."""

    recent_rate_limits: int = 0
    """How many 429/rate-limit responses this domain has received."""

    recent_antibot_blocks: int = 0
    """How many anti-bot/captcha blocks this domain has received."""

    total_attempts: int = 0
    """Total fetch attempts recorded for this domain."""


class DomainRuntimePolicy:
    """Lightweight per-domain runtime policy store.

    Thread-safe for single-process async use (no locks needed for asyncio).

    This is NOT a full scheduler — it only stores policy state that the
    fetch layer queries before sending requests.
    """

    def __init__(self) -> None:
        self._entries: dict[str, DomainPolicyEntry] = {}

    def _domain_key(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def get_or_create(self, url: str) -> DomainPolicyEntry:
        """Get the policy entry for *url*, creating one if absent."""
        key = self._domain_key(url)
        if key not in self._entries:
            self._entries[key] = DomainPolicyEntry(domain=key)
        return self._entries[key]

    # ── Mutators ──────────────────────────────────────────────────────────

    def record_success(self, url: str) -> None:
        """Record a successful fetch — resets failure counters."""
        entry = self.get_or_create(url)
        entry.recent_failures = 0
        entry.total_attempts += 1

    def record_failure(self, url: str, failure_type: str = "") -> None:
        """Record a failed fetch.

        If the failure type indicates rate-limiting or anti-bot blocking,
        those counters are incremented separately.

        When consecutive failures reach ``_COOLDOWN_FAILURE_LIMIT`` the
        domain enters cooldown.
        """
        entry = self.get_or_create(url)
        entry.recent_failures += 1
        entry.total_attempts += 1

        if "rate_limit" in failure_type.lower() or "429" in failure_type:
            entry.recent_rate_limits += 1
        if "anti_bot" in failure_type.lower() or "block" in failure_type.lower():
            entry.recent_antibot_blocks += 1

        if entry.recent_failures >= _COOLDOWN_FAILURE_LIMIT:
            entry.cooldown_until = time.monotonic() + _DEFAULT_COOLDOWN_SECONDS
            logger.info(
                "[DomainPolicy] %s entered cooldown for %ss after %d failures",
                entry.domain,
                _DEFAULT_COOLDOWN_SECONDS,
                entry.recent_failures,
            )

    def set_reduce_concurrency(self, url: str) -> None:
        """Reduce per-domain parallelism (called by recovery ``REDUCE_CONCURRENCY``)."""
        entry = self.get_or_create(url)
        entry.max_parallel = max(1, entry.max_parallel - 1)
        logger.info(
            "[DomainPolicy] %s max_parallel reduced to %d",
            entry.domain,
            entry.max_parallel,
        )

    def set_abort_domain(self, url: str) -> None:
        """Set an extended cooldown for this domain (abort/abandon)."""
        entry = self.get_or_create(url)
        entry.cooldown_until = time.monotonic() + _DEFAULT_COOLDOWN_SECONDS * 3
        logger.warning(
            "[DomainPolicy] %s aborted — cooldown until %.1f",
            entry.domain,
            entry.cooldown_until,
        )

    # ── Queries ───────────────────────────────────────────────────────────

    def can_fetch(self, url: str) -> bool:
        """Return True if the domain is not in cooldown."""
        entry = self.get_or_create(url)
        if entry.cooldown_until > time.monotonic():
            return False
        return True

    def remaining_cooldown(self, url: str) -> float:
        """Seconds remaining in cooldown (0 if not cooling)."""
        entry = self.get_or_create(url)
        remaining = entry.cooldown_until - time.monotonic()
        return max(remaining, 0.0)

    def recommended_action(self, url: str) -> str:
        """Truthful recommended action based on current policy state."""
        entry = self.get_or_create(url)
        if entry.cooldown_until > time.monotonic():
            remaining = int(self.remaining_cooldown(url))
            if entry.recent_antibot_blocks > 0:
                return f"use_authorized_access_or_retry_later (domain in cooldown for {remaining}s after anti-bot blocks)"
            if entry.recent_rate_limits > 0:
                return f"retry_later (domain rate-limited, cooldown {remaining}s)"
            return f"retry_later (domain in cooldown for {remaining}s)"
        if entry.recent_antibot_blocks > 2:
            return "use_authorized_access_or_retry_later"
        if entry.recent_rate_limits > 2:
            return "retry_later_or_reduce_request_rate"
        return "inspect_failure_telemetry"

    def get_summary(self) -> dict:
        """Return a snapshot of all tracked domains (for observability)."""
        return {
            key: {
                "max_parallel": e.max_parallel,
                "cooldown_remaining": max(0.0, e.cooldown_until - time.monotonic()),
                "recent_failures": e.recent_failures,
                "recent_rate_limits": e.recent_rate_limits,
                "recent_antibot_blocks": e.recent_antibot_blocks,
                "total_attempts": e.total_attempts,
            }
            for key, e in self._entries.items()
        }


# ── Global singleton ──────────────────────────────────────────────────────

_policy: DomainRuntimePolicy | None = None


def get_domain_runtime_policy() -> DomainRuntimePolicy:
    global _policy
    if _policy is None:
        _policy = DomainRuntimePolicy()
    return _policy


def reset_domain_runtime_policy() -> None:
    global _policy
    _policy = None
