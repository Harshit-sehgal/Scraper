"""Crawl Frontier — Priority-based URL management for large-scale crawling.

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
from pathlib import Path
from urllib.parse import urlparse

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.crawl_policy import get_crawl_policy

logger = logging.getLogger(__name__)


# ─── SQLite DB helper functions for threadpool-safe execution ─────────


def _db_insert_queue(db_path: str, priority: int, url: str, depth: int, source_url: str | None, added_at: float) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO queue VALUES (?, ?, ?, ?, ?)",
            (priority, url, depth, source_url, added_at),
        )
        conn.commit()


def _db_delete_queue(db_path: str, url: str) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM queue WHERE url = ?", (url,))
        conn.commit()


def _db_mark_completed(db_path: str, url: str) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM queue WHERE url = ?", (url,))
        conn.execute("DELETE FROM failed WHERE url = ?", (url,))
        conn.execute("INSERT OR REPLACE INTO completed VALUES (?)", (url,))
        conn.commit()


def _db_mark_failed(db_path: str, url: str, count: int) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM queue WHERE url = ?", (url,))
        conn.execute("INSERT OR REPLACE INTO failed VALUES (?, ?)", (url, count))
        conn.commit()


def _db_finalize_failed_as_completed(db_path: str, url: str) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM failed WHERE url = ?", (url,))
        conn.execute("INSERT OR REPLACE INTO completed VALUES (?)", (url,))
        conn.commit()


@dataclass(order=True)
class CrawlItem:
    priority: int
    url: str = field(compare=False)
    depth: int = field(compare=False)
    source_url: str | None = field(default=None, compare=False)
    added_at: float = field(default_factory=time.time, compare=False)


class CrawlFrontier:
    """Manages the lifecycle of URLs in a large-scale crawl."""

    def __init__(self) -> None:
        self._queue: list[CrawlItem] = []
        self._pending: set[str] = set()
        self._completed: set[str] = set()
        self._failed: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._policy = get_crawl_policy()
        self._max_discovery_depth: int = 3
        # Whether we're integrated with the scraper
        self._integrated_frontier: bool = True

        self._domain_page_counts: dict[str, int] = {}

        # Persistent SQLite storage
        # Resolve path relative to the backend directory (project_root / backend/)
        # __file__ is backend / app / crawl_frontier.py → .parent.parent =
        # backend/
        backend_root = Path(__file__).resolve().parent.parent
        self._db_path = str(backend_root / "data" / "crawl_frontier.db")
        self._init_db()
        self._load_from_db()

    def _init_db(self) -> None:
        import sqlite3

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    priority INTEGER,
                    url TEXT PRIMARY KEY,
                    depth INTEGER,
                    source_url TEXT,
                    added_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS completed (
                    url TEXT PRIMARY KEY
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failed (
                    url TEXT PRIMARY KEY,
                    count INTEGER
                )
            """)
            conn.commit()

    def _load_from_db(self) -> None:
        import heapq
        import sqlite3
        from urllib.parse import urlparse

        try:
            with sqlite3.connect(self._db_path) as conn:
                # Load completed
                for row in conn.execute("SELECT url FROM completed"):
                    self._completed.add(row[0])
                    domain = urlparse(row[0]).netloc
                    self._domain_page_counts[domain] = self._domain_page_counts.get(domain, 0) + 1

                # Load failed
                for row in conn.execute("SELECT url, count FROM failed"):
                    self._failed[row[0]] = row[1]

                # Load queue
                for row in conn.execute("SELECT priority, url, depth, source_url, added_at FROM queue"):
                    if row[1] not in self._completed:
                        item = CrawlItem(priority=row[0], url=row[1], depth=row[2], source_url=row[3], added_at=row[4])
                        self._queue.append(item)
                        self._pending.add(row[1])

                # Heapify to establish priority invariant
                heapq.heapify(self._queue)
        except Exception:
            logger.exception("Failed to load frontier state from SQLite: %s")

    async def add_url(self, url: str, priority: int = 10, depth: int = 0, source_url: str | None = None) -> bool:
        """Add a URL to the frontier if it hasn't been crawled yet."""
        if not url or not url.startswith("http"):
            return False

        async with self._lock:
            # 1. Deduplication
            if url in self._completed or url in self._pending:
                return False

            # Enforce maximum page limits per domain to prevent infinite loops
            from urllib.parse import urlparse

            domain = urlparse(url).netloc
            if self._domain_page_counts.get(domain, 0) >= settings.CRAWL_MAX_PAGES_PER_DOMAIN:
                logger.debug(
                    "[Frontier] Domain page limit hit for %s (%d >= %d). Rejecting URL: %s",
                    domain,
                    self._domain_page_counts.get(domain, 0),
                    settings.CRAWL_MAX_PAGES_PER_DOMAIN,
                    url,
                )
                return False

            # 2. Priority calculation (lower = higher priority)
            # Higher depth = lower priority
            item_priority = priority + (depth * 5)

            item = CrawlItem(priority=item_priority, url=url, depth=depth, source_url=source_url)
            heapq.heappush(self._queue, item)
            self._pending.add(url)

            try:
                await run_in_threadpool(
                    _db_insert_queue,
                    self._db_path,
                    item_priority,
                    url,
                    depth,
                    source_url,
                    item.added_at,
                )
            except Exception:
                logger.exception("Failed to insert URL into SQLite: %s")

            logger.debug("[Frontier] Added URL: %s (depth: %d, priority: %d)", url, depth, item_priority)
            return True

    async def get_next_url(self) -> str | None:
        """Get the next URL available for crawling, respecting policy."""
        tried: list[CrawlItem] = []
        max_retries = 1000  # safety valve: prevent unbounded queue scan
        retries = 0

        while retries < max_retries:
            retries += 1
            # 1. Pop a candidate item under the lock
            async with self._lock:
                if not self._queue:
                    # No more items in queue! Restore tried items before
                    # returning  # noqa: ERA001
                    for item in tried:
                        if item.url not in self._completed:
                            heapq.heappush(self._queue, item)
                            self._pending.add(item.url)
                            try:
                                await run_in_threadpool(
                                    _db_insert_queue,
                                    self._db_path,
                                    item.priority,
                                    item.url,
                                    item.depth,
                                    item.source_url,
                                    item.added_at,
                                )
                            except Exception:
                                logger.exception("Failed to restore URL to SQLite: %s")
                    return None

                item = heapq.heappop(self._queue)
                # Temporarily remove from pending during active policy check
                self._pending.discard(item.url)

                try:
                    await run_in_threadpool(_db_delete_queue, self._db_path, item.url)
                except Exception:
                    logger.exception("Failed to delete URL from SQLite queue: %s")

            # 2. Release lock and evaluate policy check asynchronously outside
            # the lock
            block_reason = await self._policy.check_domain(item.url)

            if not block_reason:
                # Target is eligible! Restore its pending status and return
                async with self._lock:
                    self._pending.add(item.url)
                    try:
                        await run_in_threadpool(
                            _db_insert_queue,
                            self._db_path,
                            item.priority,
                            item.url,
                            item.depth,
                            item.source_url,
                            item.added_at,
                        )
                    except Exception:
                        logger.exception("Failed to restore URL to SQLite: %s")
                    # Restore other tried items under the lock
                    for t_item in tried:
                        if t_item.url not in self._completed:
                            heapq.heappush(self._queue, t_item)
                            self._pending.add(t_item.url)
                            try:
                                await run_in_threadpool(
                                    _db_insert_queue,
                                    self._db_path,
                                    t_item.priority,
                                    t_item.url,
                                    t_item.depth,
                                    t_item.source_url,
                                    t_item.added_at,
                                )
                            except Exception:
                                logger.exception("Failed to restore tried URL to SQLite: %s")
                return item.url
            # Blocked! Restore pending status and track in tried list
            async with self._lock:
                self._pending.add(item.url)
                try:
                    await run_in_threadpool(
                        _db_insert_queue,
                        self._db_path,
                        item.priority,
                        item.url,
                        item.depth,
                        item.source_url,
                        item.added_at,
                    )
                except Exception:
                    logger.exception("Failed to save blocked URL: %s")
            tried.append(item)

            if len(tried) > 20:  # Don't look too deep
                break

        # 3. If we searched too deep and didn't find any eligible URL,
        # restore all tried items to the heap under the lock.
        async with self._lock:
            for item in tried:
                if item.url not in self._completed:
                    heapq.heappush(self._queue, item)
                    self._pending.add(item.url)
                    try:
                        await run_in_threadpool(
                            _db_insert_queue,
                            self._db_path,
                            item.priority,
                            item.url,
                            item.depth,
                            item.source_url,
                            item.added_at,
                        )
                    except Exception:
                        logger.exception("Failed to restore tried URLs: %s")
        return None

    async def mark_completed(self, url: str, success: bool = True) -> None:
        """Mark a URL as completed or failed."""
        async with self._lock:
            if url in self._pending:
                self._pending.remove(url)

            if success:
                self._completed.add(url)
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
                self._domain_page_counts[domain] = self._domain_page_counts.get(domain, 0) + 1
                self._failed.pop(url, None)
                try:
                    await run_in_threadpool(_db_mark_completed, self._db_path, url)
                except Exception:
                    logger.exception("Failed to mark completed in SQLite: %s")
            else:
                count = self._failed.get(url, 0) + 1
                self._failed[url] = count
                try:
                    await run_in_threadpool(_db_mark_failed, self._db_path, url, count)
                except Exception:
                    logger.exception("Failed to update failed count in SQLite: %s")

                # Retry logic: if not too many failures, put back in queue with
                # lower priority
                if count < settings.CRAWL_MAX_RETRIES_PER_DOMAIN:
                    item = CrawlItem(priority=100 + (count * 20), url=url, depth=0)
                    heapq.heappush(self._queue, item)
                    self._pending.add(url)
                    try:
                        await run_in_threadpool(
                            _db_insert_queue,
                            self._db_path,
                            item.priority,
                            url,
                            item.depth,
                            item.source_url,
                            item.added_at,
                        )
                    except Exception:
                        logger.exception("Failed to insert retry URL in SQLite: %s")
                else:
                    # Move to completed to stop retrying
                    self._completed.add(url)
                    from urllib.parse import urlparse

                    domain = urlparse(url).netloc
                    self._domain_page_counts[domain] = self._domain_page_counts.get(domain, 0) + 1
                    try:
                        await run_in_threadpool(_db_finalize_failed_as_completed, self._db_path, url)
                    except Exception:
                        logger.exception("Failed to finalize failed URL as completed in SQLite: %s")

    async def add_discovered_links(self, links: list[str], source_url: str, source_depth: int = 0) -> int:
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
            logger.debug("[Frontier] Added %d discovered links from %s (depth %d)", added, source_url, source_depth)
        return added

    async def get_next_urls(self, count: int = 5) -> list[str]:
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

    async def get_frontier_for_domain(self, domain: str, max_urls: int = 10) -> list[str]:
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

                    try:
                        await run_in_threadpool(_db_delete_queue, self._db_path, item.url)
                    except Exception:
                        logger.exception("Failed to delete domain URL from SQLite: %s")
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
