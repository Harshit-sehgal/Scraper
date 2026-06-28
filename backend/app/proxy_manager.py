"""Proxy Manager — Anti-Bot Evasion via Proxy Rotation.

Responsible for:
- Managing a pool of proxy servers
- Rotating proxies when failures accumulate
- Tracking proxy health and availability
- Integrating with Playwright for proxy use
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any

from app.config import settings
from app.utils.log_redaction import mask_proxy_url

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy rotation for anti-bot resilience.

    Thread safety: all mutating methods are guarded by ``_lock`` so
    concurrent callers from the anti-bot engine, browser pool, and
    request handlers can safely mutate the shared state.
    """

    # If a proxy accumulates this many total failures (not reset by
    # rotation or success decay), it is evicted permanently from the
    # pool.  Prevents dead proxies from being retried indefinitely after
    # domain-blocked lists are cleared.
    _EVICTION_TOTAL_FAILURES = 15

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proxy_list: list[str] = []
        self._current_index: int = 0
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)
        self._total_failure_counts: dict[str, int] = defaultdict(int)  # cumulative, never reset
        self._enabled: bool = settings.PROXY_ROTATION_ENABLED
        self._consecutive_failures: int = 0  # Track across all proxies
        self._proxy_blocked_domains: dict[str, set[str]] = defaultdict(set)  # proxy -> domains blocked on
        self._provider: Any | None = None  # ProxyProvider for plug-in sources (None = static)

        # Load proxies: provider first, then env var fallback.
        #
        # Resolution order:
        #   1. PROXY_PROVIDER_TYPE != "static" → delegate to
        #      :func:`app.proxy_providers.create_provider`.
        #   2. PROXY_PROVIDER_TYPE == "static" (default) → read
        #      PROXY_LIST env var.
        self._load_initial_proxies()

    def _load_initial_proxies(self) -> None:
        """Populate ``_proxy_list`` from the configured provider or env var.

        Split out of ``__init__`` so tests and refresh routines can call
        it without re-entering the constructor.
        """
        if not self._enabled:
            return

        provider_type = ""
        try:
            from app.config import settings

            provider_type = (settings.PROXY_PROVIDER_TYPE or "static").strip().lower()
        except ImportError:
            provider_type = "static"

        if provider_type and provider_type != "static":
            try:
                from app.proxy_providers import create_provider

                provider = create_provider()
                loaded = provider.fetch_proxies()
                self._proxy_list = list(loaded)
                self._provider = provider
                logger.info(
                    "Proxy manager initialized via '%s' provider with %d proxies",
                    provider_type,
                    len(self._proxy_list),
                )
                return
            except (ImportError, RuntimeError, ValueError, OSError) as exc:
                logger.warning(
                    "Provider '%s' failed (%s); falling back to PROXY_LIST", provider_type, exc
                )

        if settings.PROXY_LIST:
            self._proxy_list = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]
            logger.info(
                "Proxy manager initialized with %d proxies from PROXY_LIST", len(self._proxy_list)
            )
        else:
            logger.warning("Proxy rotation enabled but PROXY_LIST is empty")

    def set_provider(self, provider: Any) -> None:
        """Override the configured provider (test-only helper).

        Replaces ``_provider`` without otherwise disturbing rotation
        state.  The provider is *not* immediately fetched — call
        :meth:`refresh_from_provider` to swap the pool.
        """
        with self._lock:
            self._provider = provider

    def refresh_from_provider(self) -> int:
        """Re-fetch the proxy list from the configured provider.

        Returns the number of proxies now in the pool (0 if no provider
        is configured or the fetch failed).  Acquired proxies are
        replaced wholesale so stale entries vanish on the next rotation.
        """
        with self._lock:
            if self._provider is None:
                return len(self._proxy_list)
            try:
                fresh = self._provider.refresh()
            except (RuntimeError, ValueError, OSError) as exc:
                logger.warning("Provider refresh failed: %s", exc)
                return len(self._proxy_list)
            self._proxy_list = [str(p).strip() for p in fresh if str(p).strip()]
            self._current_index = 0
            logger.info("Proxy pool refreshed via provider: %d proxies", len(self._proxy_list))
            return len(self._proxy_list)

    @property
    def enabled(self) -> bool:
        """Whether proxy rotation is enabled."""
        return self._enabled and bool(self._proxy_list)

    @property
    def current_proxy(self) -> str | None:
        """Get the current proxy without rotating (thread-safe read)."""
        with self._lock:
            if not self._enabled or not self._proxy_list:
                return None
            return self._proxy_list[self._current_index % len(self._proxy_list)]

    def record_failure(self, proxy: str | None = None, domain: str | None = None) -> None:
        """Record a failure for the given proxy (or current).

        If a proxy's cumulative failure count exceeds the eviction
        threshold, it is permanently removed from the pool so that
        dead proxies are not retried indefinitely.
        """
        if not self.enabled:
            return

        with self._lock:
            proxy = proxy or self._proxy_list[self._current_index % len(self._proxy_list)] if self._proxy_list else None
            if not proxy:
                return

            self._failure_counts[proxy] += 1
            self._total_failure_counts[proxy] += 1
            self._consecutive_failures += 1

            # Track domain-specific proxy blocking
            if domain:
                self._proxy_blocked_domains[proxy].add(domain)

            # ── Dead proxy eviction ────────────────────────────────────
            cumulative = self._total_failure_counts[proxy]
            if cumulative >= self._EVICTION_TOTAL_FAILURES:
                self._evict_proxy(proxy)
                return

            # Rotate if threshold exceeded
            if self._failure_counts[proxy] >= settings.PROXY_ROTATION_FAILURE_THRESHOLD:
                logger.warning("Proxy %s reached %d failures, rotating", mask_proxy_url(proxy), self._failure_counts[proxy])
                self._rotate_locked(domain=domain)
                self._failure_counts[proxy] = 0

    def record_success(self, proxy: str | None = None, domain: str | None = None) -> None:
        """Record a success for the given proxy (or current).

        ``domain`` is accepted for API symmetry with ``record_failure`` but
        does not currently affect success tracking.
        """
        if not self.enabled:
            return

        with self._lock:
            proxy = proxy or self._proxy_list[self._current_index % len(self._proxy_list)] if self._proxy_list else None
            if not proxy:
                return

            self._success_counts[proxy] += 1
            self._consecutive_failures = 0
            # Decay the failure counter rather than wiping it. The previous
            # behavior (set to 0 on a single success) let a proxy burn 9 of
            # its failure budget, succeed once, and immediately re-enter the
            # pool with no memory of recent trouble — which meant
            # PROXY_ROTATION_FAILURE_THRESHOLD could be reset by a single
            # lucky success and the proxy would be chosen again on the next
            # domain.
            prior_failures = self._failure_counts.get(proxy, 0)
            if prior_failures > 0:
                self._failure_counts[proxy] = max(0, prior_failures - 1)

    def _evict_proxy(self, proxy: str) -> None:
        """Permanently remove a dead proxy from the pool.

        Called when a proxy's cumulative failure count exceeds
        ``_EVICTION_TOTAL_FAILURES``.  Cleans up all associated tracking
        state (failure counts, success counts, domain blocks) and removes
        the proxy from rotation.

        Must be called while holding ``self._lock``.
        """
        if proxy not in self._proxy_list:
            return

        logger.warning(
            "Evicting dead proxy %s (cumulative failures: %d, remaining pool: %d)",
            mask_proxy_url(proxy),
            self._total_failure_counts.get(proxy, 0),
            len(self._proxy_list) - 1,
        )

        self._proxy_list.remove(proxy)
        self._failure_counts.pop(proxy, None)
        self._success_counts.pop(proxy, None)
        self._total_failure_counts.pop(proxy, None)
        self._proxy_blocked_domains.pop(proxy, None)

        # Clamp the index so subsequent rotations don't IndexError
        if self._proxy_list:
            self._current_index = self._current_index % len(self._proxy_list)
        else:
            self._current_index = 0
            self._enabled = False
            logger.warning("All proxies evicted — proxy rotation disabled")

    def _rotate_locked(self, domain: str | None = None) -> str | None:
        """Internal rotate — caller already holds ``self._lock``.

        If domain is provided, marks the current proxy as blocked for that domain
        and skips proxies that have been blocked for it.
        """
        if not self._enabled or not self._proxy_list:
            return None

        # Record which proxy is blocked for which domain
        current = self._proxy_list[self._current_index % len(self._proxy_list)]
        if domain and current:
            self._proxy_blocked_domains[current].add(domain)
            logger.debug("Proxy %s blocked for domain %s", mask_proxy_url(current), domain)

        # Find next proxy that isn't blocked for this domain
        starting_index = self._current_index
        attempts = 0
        while attempts < len(self._proxy_list):
            self._current_index = (self._current_index + 1) % len(self._proxy_list)
            candidate = self._proxy_list[self._current_index]
            if (
                domain is None
                or candidate not in self._proxy_blocked_domains
                or domain not in self._proxy_blocked_domains[candidate]
            ):
                break
            attempts += 1
            if self._current_index == starting_index:
                # All proxies blocked for this domain — reset blocked set
                logger.warning("All proxies blocked for domain %s, resetting blocked list", domain)
                self._proxy_blocked_domains.clear()
                break

        new_proxy = self._proxy_list[self._current_index]
        logger.debug("Rotated to proxy: %s", mask_proxy_url(new_proxy))
        return new_proxy

    def rotate(self, domain: str | None = None) -> str | None:
        """Explicitly rotate to the next proxy (thread-safe).

        If domain is provided, marks the current proxy as blocked for that domain
        and skips proxies that have been blocked for it.
        """
        with self._lock:
            return self._rotate_locked(domain=domain)

    def reset_consecutive_failures(self) -> None:
        """Reset consecutive failure counter on successful request."""
        with self._lock:
            self._consecutive_failures = 0

    def get_best_proxy(self, domain: str | None = None) -> str | None:
        """Get the best proxy for a domain based on health stats (thread-safe).

        Selects the proxy with the highest success rate that isn't
        blocked for the given domain.
        """
        with self._lock:
            if not self._enabled or not self._proxy_list:
                return None

            candidates = []
            for proxy in self._proxy_list:
                # Skip proxies blocked for this domain
                if domain and proxy in self._proxy_blocked_domains and domain in self._proxy_blocked_domains[proxy]:
                    continue

                success = self._success_counts.get(proxy, 0)
                failure = self._failure_counts.get(proxy, 0)
                total = success + failure
                rate = (success / total) if total > 0 else 0.5
                candidates.append((rate, proxy))

            if not candidates:
                return self._proxy_list[self._current_index % len(self._proxy_list)]

            # Return proxy with highest success rate
            candidates.sort(key=lambda x: -x[0])
            return candidates[0][1]

    def get_proxy_for_playwright(self) -> dict | None:
        """Return proxy config dict for Playwright context creation.

        Format: {"server": "http://ip:port"} or {"server": "socks5://ip:port"}
        """
        if not self.enabled or not self.current_proxy:
            return None

        return {"server": self.current_proxy}

    def get_health_stats(self) -> dict[str, Any]:
        """Return health statistics for all proxies (thread-safe read)."""
        with self._lock:
            stats = {}
            for proxy in self._proxy_list:
                success = self._success_counts.get(proxy, 0)
                failure = self._failure_counts.get(proxy, 0)
                total = success + failure
                success_rate = (success / total * 100) if total > 0 else 0

                stats[proxy] = {
                    "successes": success,
                    "failures": failure,
                    "total_attempts": total,
                    "success_rate": success_rate,
                    "health": "healthy" if success_rate >= 70 else "degraded" if success_rate >= 30 else "unhealthy",
                }

            return stats


# Global singleton
_proxy_manager: ProxyManager | None = None
_proxy_manager_lock = __import__("threading").Lock()


def get_proxy_manager() -> ProxyManager:
    """Get or create the global proxy manager instance."""
    global _proxy_manager
    if _proxy_manager is None:
        with _proxy_manager_lock:
            if _proxy_manager is None:
                _proxy_manager = ProxyManager()
    return _proxy_manager
