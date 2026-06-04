"""Proxy Manager — Anti-Bot Evasion via Proxy Rotation.

Responsible for:
- Managing a pool of proxy servers
- Rotating proxies when failures accumulate
- Tracking proxy health and availability
- Integrating with Playwright for proxy use
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.config import settings

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy rotation for anti-bot resilience."""

    def __init__(self) -> None:
        self._proxy_list: list[str] = []
        self._current_index: int = 0
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)
        self._enabled: bool = settings.PROXY_ROTATION_ENABLED
        self._consecutive_failures: int = 0  # Track across all proxies
        self._proxy_blocked_domains: dict[str, set[str]] = defaultdict(set)  # proxy -> domains blocked on

        # Load proxies from config if available
        if self._enabled and settings.PROXY_LIST:
            self._proxy_list = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]
            logger.info("Proxy manager initialized with %d proxies", len(self._proxy_list))
        elif self._enabled:
            logger.warning("Proxy rotation enabled but PROXY_LIST is empty")

    @property
    def enabled(self) -> bool:
        """Whether proxy rotation is enabled."""
        return self._enabled and bool(self._proxy_list)

    @property
    def current_proxy(self) -> str | None:
        """Get the current proxy without rotating."""
        if not self.enabled:
            return None
        return self._proxy_list[self._current_index % len(self._proxy_list)]

    def record_failure(self, proxy: str | None = None, domain: str | None = None) -> None:
        """Record a failure for the given proxy (or current)."""
        if not self.enabled:
            return

        proxy = proxy or self.current_proxy
        if not proxy:
            return

        self._failure_counts[proxy] += 1
        self._consecutive_failures += 1

        # Track domain-specific proxy blocking
        if domain:
            self._proxy_blocked_domains[proxy].add(domain)

        # Rotate if threshold exceeded
        if self._failure_counts[proxy] >= settings.PROXY_ROTATION_FAILURE_THRESHOLD:
            logger.warning("Proxy %s reached %d failures, rotating", proxy, self._failure_counts[proxy])
            self.rotate(domain=domain)
            self._failure_counts[proxy] = 0

    def record_success(self, proxy: str | None = None) -> None:
        """Record a success for the given proxy (or current)."""
        if not self.enabled:
            return

        proxy = proxy or self.current_proxy
        if not proxy:
            return

        self._success_counts[proxy] += 1
        self._consecutive_failures = 0
        self._failure_counts[proxy] = 0

    def rotate(self, domain: str | None = None) -> str | None:
        """Explicitly rotate to the next proxy.

        If domain is provided, marks the current proxy as blocked for that domain
        and skips proxies that have been blocked for it.
        """
        if not self.enabled:
            return None

        # Record which proxy is blocked for which domain
        current = self.current_proxy
        if domain and current:
            self._proxy_blocked_domains[current].add(domain)
            logger.debug("Proxy %s blocked for domain %s", current, domain)

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
        logger.debug("Rotated to proxy: %s", new_proxy)
        return new_proxy

    def reset_consecutive_failures(self) -> None:
        """Reset consecutive failure counter on successful request."""
        self._consecutive_failures = 0

    def get_best_proxy(self, domain: str | None = None) -> str | None:
        """Get the best proxy for a domain based on health stats.

        Selects the proxy with the highest success rate that isn't
        blocked for the given domain.
        """
        if not self.enabled:
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
            return self.current_proxy

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

    def get_health_stats(self) -> dict:
        """Return health statistics for all proxies."""
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


def get_proxy_manager() -> ProxyManager:
    """Get or create the global proxy manager instance."""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
