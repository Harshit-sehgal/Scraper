"""Crawl State Adapter — isolated state management for the crawl layer."""

from __future__ import annotations

import logging

from app.crawl_frontier import get_crawl_frontier
from app.crawl_policy import get_crawl_policy

logger = logging.getLogger(__name__)


class CrawlStateAdapter:
    """Delegated state manager for Crawl Frontier, Pacing, and Budgets."""

    def __init__(self) -> None:
        self._frontier = get_crawl_frontier()
        self._policy = get_crawl_policy()

    async def add_url(self, url: str, priority: int = 10, depth: int = 0, source_url: str | None = None) -> bool:
        """Add a URL to the frontier queue."""
        return await self._frontier.add_url(url, priority, depth, source_url)

    async def get_next_urls(self, count: int = 5) -> list[str]:
        """Fetch the next batch of eligible URLs to crawl."""
        return await self._frontier.get_next_urls(count)

    async def mark_completed(self, url: str, success: bool = True) -> None:  # noqa: FBT001, FBT002
        """Mark a crawl task as completed or failed and update policy budgets."""
        await self._frontier.mark_completed(url, success)
        self._policy.record_result(url, success)

    async def add_discovered_links(self, links: list[str], source_url: str, source_depth: int = 0) -> int:
        """Enqueue newly discovered links from a scraped page."""
        return await self._frontier.add_discovered_links(links, source_url, source_depth)

    def get_stats(self) -> dict:
        """Fetch operational stats from policy engine and frontier."""
        return {
            "frontier": self._frontier.get_stats(),
            "policy": self._policy.get_all_domain_states(),
        }

    def get_domain_health(self, domain: str) -> float:
        """Retrieve computed health score for a target domain."""
        return self._policy.get_domain_health_score(domain)


_crawl_state: CrawlStateAdapter | None = None


def get_crawl_state() -> CrawlStateAdapter:
    global _crawl_state
    if _crawl_state is None:
        _crawl_state = CrawlStateAdapter()
    return _crawl_state
