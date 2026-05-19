"""
Crawl Frontier — Priority-based URL management for large-scale crawling.

Responsible for:
- Prioritizing URLs based on domain reputation and depth.
- Deduplication of pending and completed URLs.
- Domain-level budget enforcement (relying on CrawlPolicyEngine).
- Adaptive pacing hooks.
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from app.config import settings
from app.crawl_policy import get_crawl_policy

logger = logging.getLogger(__name__)


@dataclass(order=True)
class CrawlItem:
    priority: int
    url: str = field(compare=False)
    depth: int = field(compare=False)
    source_url: Optional[str] = field(default=None, compare=False)
    added_at: float = field(default_factory=time.time, compare=False)


class CrawlFrontier:
    """Manages the lifecycle of URLs in a large-scale crawl."""

    def __init__(self) -> None:
        self._queue: List[CrawlItem] = []
        self._pending: Set[str] = set()
        self._completed: Set[str] = set()
        self._failed: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._policy = get_crawl_policy()
        self._max_discovery_depth: int = 3
        self._integrated_frontier: bool = True  # Whether we're integrated with the scraper

    async def add_url(
        self, 
        url: str, 
        priority: int = 10, 
        depth: int = 0, 
        source_url: Optional[str] = None
    ) -> bool:
        """Add a URL to the frontier if it hasn't been crawled yet."""
        if not url or not url.startswith("http"):
            return False

        async with self._lock:
            # 1. Deduplication
            if url in self._completed or url in self._pending:
                return False
            
            # 2. Priority calculation (lower = higher priority)
            # Higher depth = lower priority
            item_priority = priority + (depth * 5)
            
            item = CrawlItem(priority=item_priority, url=url, depth=depth, source_url=source_url)
            heapq.heappush(self._queue, item)
            self._pending.add(url)
            
            logger.debug("[Frontier] Added URL: %s (depth: %d, priority: %d)", url, depth, item_priority)
            return True

    async def get_next_url(self) -> Optional[str]:
        """Get the next URL available for crawling, respecting policy."""
        tried = []
        next_url = None

        while True:
            # 1. Pop a candidate item under the lock
            async with self._lock:
                if not self._queue:
                    # No more items in queue! Restore tried items before returning
                    for item in tried:
                        if item.url not in self._completed:
                            heapq.heappush(self._queue, item)
                    return None
                
                item = heapq.heappop(self._queue)
                # Temporarily remove from pending during active policy check
                self._pending.discard(item.url)

            # 2. Release lock and evaluate policy check asynchronously outside the lock
            block_reason = await self._policy.check_domain(item.url)

            if not block_reason:
                # Target is eligible! Restore its pending status and return
                async with self._lock:
                    self._pending.add(item.url)
                    # Restore other tried items under the lock
                    for t_item in tried:
                        if t_item.url not in self._completed:
                            heapq.heappush(self._queue, t_item)
                            self._pending.add(t_item.url)
                return item.url
            else:
                # Blocked! Restore pending status and track in tried list
                async with self._lock:
                    self._pending.add(item.url)
                tried.append(item)

                if len(tried) > 20: # Don't look too deep
                    break

        # 3. If we searched too deep and didn't find any eligible URL,
        # restore all tried items to the heap under the lock.
        async with self._lock:
            for item in tried:
                if item.url not in self._completed:
                    heapq.heappush(self._queue, item)
                    self._pending.add(item.url)
        return None

    async def mark_completed(self, url: str, success: bool = True):
        """Mark a URL as completed or failed."""
        async with self._lock:
            if url in self._pending:
                self._pending.remove(url)
            
            if success:
                self._completed.add(url)
                self._failed.pop(url, None)
            else:
                count = self._failed.get(url, 0) + 1
                self._failed[url] = count
                
                # Retry logic: if not too many failures, put back in queue with lower priority
                if count < settings.CRAWL_MAX_RETRIES_PER_DOMAIN:
                    item = CrawlItem(priority=100 + (count * 20), url=url, depth=0)
                    heapq.heappush(self._queue, item)
                    self._pending.add(url)
                else:
                    self._completed.add(url) # Move to completed to stop retrying

    async def add_discovered_links(self, links: List[str], source_url: str, source_depth: int = 0) -> int:
        """Add links discovered during extraction back to the frontier.
        
        This implements the crawl orchestration loop:
          scrape_url → discover_links → add_to_frontier → scrape_next_url
        
        Args:
            links: URLs discovered during extraction
            source_url: The URL they were discovered from
            source_depth: Current crawl depth
            
        Returns:
            Number of new URLs added (after dedup)
        """
        if not self._integrated_frontier:
            return 0
        
        added = 0
        for link in links:
            new_depth = source_depth + 1
            if new_depth <= self._max_discovery_depth:
                success = await self.add_url(link, depth=new_depth, source_url=source_url)
                if success:
                    added += 1
        
        if added > 0:
            logger.debug("[Frontier] Added %d discovered links from %s (depth %d)", 
                        added, source_url, source_depth)
        return added

    async def get_next_urls(self, count: int = 5) -> List[str]:
        """Get multiple URLs available for crawling.
        
        Useful for batch processing — returns up to `count` URLs
        that pass the crawl policy check.
        """
        urls = []
        for _ in range(count):
            url = await self.get_next_url()
            if url:
                urls.append(url)
            else:
                break
        return urls

    async def get_frontier_for_domain(self, domain: str, max_urls: int = 10) -> List[str]:
        """Get next URLs for a specific domain.
        
        Useful for domain-priority crawling where a single domain
        needs focused attention.
        
        Note: This pops URLs from the frontier heap, so they won't
        be returned by subsequent get_next_url() calls.
        """
        domain_urls: list[str] = []
        async with self._lock:
            # Collect non-matching items to re-push later
            remaining = []
            while self._queue and len(domain_urls) < max_urls:
                item = heapq.heappop(self._queue)
                if domain in urlparse(item.url).netloc:
                    domain_urls.append(item.url)
                    self._pending.discard(item.url)
                else:
                    remaining.append(item)
            # Re-push non-domain items
            for item in remaining:
                heapq.heappush(self._queue, item)
        return domain_urls

    def get_stats(self) -> dict:
        """Return frontier operational statistics."""
        return {
            "queue_size": len(self._queue),
            "pending_count": len(self._pending),
            "completed_count": len(self._completed),
            "failed_count": len(self._failed),
            "integrated": self._integrated_frontier,
        }


# Global Singleton
_frontier: CrawlFrontier | None = None

def get_crawl_frontier() -> CrawlFrontier:
    global _frontier
    if _frontier is None:
        _frontier = CrawlFrontier()
    return _frontier
