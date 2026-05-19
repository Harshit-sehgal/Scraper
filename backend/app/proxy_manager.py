"""
Proxy Manager — Anti-Bot Evasion via Proxy Rotation.

Responsible for:
- Managing a pool of proxy servers
- Rotating proxies when failures accumulate
- Tracking proxy health and availability
- Integrating with Playwright for proxy use
"""

from __future__ import annotations

import logging
from typing import Optional, List
from collections import defaultdict

from app.config import settings

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy rotation for anti-bot resilience."""

    def __init__(self) -> None:
        self._proxy_list: List[str] = []
        self._current_index: int = 0
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._success_counts: dict[str, int] = defaultdict(int)
        self._enabled: bool = settings.PROXY_ROTATION_ENABLED
        
        # Load proxies from config if available
        if self._enabled and settings.PROXY_LIST:
            self._proxy_list = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]
            logger.info(f"Proxy manager initialized with {len(self._proxy_list)} proxies")
        elif self._enabled:
            logger.warning("Proxy rotation enabled but PROXY_LIST is empty")

    @property
    def enabled(self) -> bool:
        """Whether proxy rotation is enabled."""
        return self._enabled and bool(self._proxy_list)

    @property
    def current_proxy(self) -> Optional[str]:
        """Get the current proxy without rotating."""
        if not self.enabled:
            return None
        return self._proxy_list[self._current_index % len(self._proxy_list)]

    def record_failure(self, proxy: Optional[str] = None) -> None:
        """Record a failure for the given proxy (or current)."""
        if not self.enabled:
            return
        
        proxy = proxy or self.current_proxy
        if not proxy:
            return
        
        self._failure_counts[proxy] += 1
        
        # Rotate if threshold exceeded
        if self._failure_counts[proxy] >= settings.PROXY_ROTATION_FAILURE_THRESHOLD:
            logger.warning(
                f"Proxy {proxy} reached {self._failure_counts[proxy]} failures, rotating"
            )
            self.rotate()
            self._failure_counts[proxy] = 0

    def record_success(self, proxy: Optional[str] = None) -> None:
        """Record a success for the given proxy (or current)."""
        if not self.enabled:
            return
        
        proxy = proxy or self.current_proxy
        if not proxy:
            return
        
        self._success_counts[proxy] += 1
        self._failure_counts[proxy] = max(0, self._failure_counts[proxy] - 1)

    def rotate(self) -> Optional[str]:
        """Explicitly rotate to the next proxy."""
        if not self.enabled:
            return None
        
        self._current_index = (self._current_index + 1) % len(self._proxy_list)
        new_proxy = self._proxy_list[self._current_index]
        logger.debug(f"Rotated to proxy: {new_proxy}")
        return new_proxy

    def get_proxy_for_playwright(self) -> Optional[dict]:
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
