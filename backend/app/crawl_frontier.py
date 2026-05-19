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
from typing import Dict, List, Optional, Set, Tuple
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
        async with self._lock:
            if not self._queue:
                return None
            
            # We try to find a URL that isn't blocked by policy
            # Since we can't 'peek' and skip in a heap easily without re-building,
            # we iterate through a copy or just try the top.
            # For simplicity, we'll try the top N items.
            
            tried = []
            next_url = None
            
            while self._queue:
                item = heapq.heappop(self._queue)
                
                # Check policy (non-blocking)
                # Note: check_domain is async because it might fetch robots.txt
                # We release the lock for the check? No, that's risky for the queue.
                # Actually, check_domain is usually fast after the first time.
                
                block_reason = await self._policy.check_domain(item.url)
                if not block_reason:
                    next_url = item.url
                    break
                else:
                    # Put back if not eligible yet (delay met, etc)
                    tried.append(item)
                    if len(tried) > 20: # Don't look too deep
                        break
            
            # Put back the ones we couldn't use yet
            for item in tried:
                heapq.heappush(self._queue, item)
                
            return next_url

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

    def get_stats(self) -> dict:
        """Return frontier operational statistics."""
        return {
            "queue_size": len(self._queue),
            "pending_count": len(self._pending),
            "completed_count": len(self._completed),
            "failed_count": len(self._failed)
        }


# Global Singleton
_frontier: CrawlFrontier | None = None

def get_crawl_frontier() -> CrawlFrontier:
    global _frontier
    if _frontier is None:
        _frontier = CrawlFrontier()
    return _frontier
