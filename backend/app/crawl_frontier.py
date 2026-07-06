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
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.crawl_policy import get_crawl_policy

logger = logging.getLogger(__name__)

# Exceptions that SQLite / threadpool DB operations may raise.
# Used to catch recoverable failures without masking programming bugs.
_DB_FALLBACK_ERRORS = (OSError, RuntimeError, ValueError, TypeError, ImportError, sqlite3.Error)


# ─── SQLite DB helper functions for threadpool-safe execution ─────────


def _db_insert_queue(db_path: str, priority: int, url: str, depth: int, source_url: str | None, added_at: float) -> None:
    import sqlite3

    # Resource-leak fix: ``with sqlite3.connect(...) as conn:`` only manages
    # the transaction — it does NOT close the connection. These helpers run
    # inside ``asyncio.to_thread(...)`` on every frontier enqueue/complete/
    # fail, so the leak is amplified. Use ``try/finally: conn.close()``.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO queue VALUES (?, ?, ?, ?, ?)",
            (priority, url, depth, source_url, added_at),
        )
        conn.commit()
    except _DB_FALLBACK_ERRORS:
        conn.rollback()
        raise
    finally:
        conn.close()


def _db_delete_queue(db_path: str, url: str) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM queue WHERE url = ?", (url,))
        conn.commit()
    except _DB_FALLBACK_ERRORS:
        conn.rollback()
        raise
    finally:
        conn.close()


def _db_mark_completed(db_path: str, url: str) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM queue WHERE url = ?", (url,))
        conn.execute("DELETE FROM failed WHERE url = ?", (url,))
        conn.execute("INSERT OR REPLACE INTO completed VALUES (?)", (url,))
        conn.commit()
    except _DB_FALLBACK_ERRORS:
        conn.rollback()
        raise
    finally:
        conn.close()


def _db_mark_failed(db_path: str, url: str, count: int) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM queue WHERE url = ?", (url,))
        conn.execute("INSERT OR REPLACE INTO failed VALUES (?, ?)", (url, count))
        conn.commit()
    except _DB_FALLBACK_ERRORS:
        conn.rollback()
        raise
    finally:
        conn.close()


def _db_finalize_failed_as_completed(db_path: str, url: str) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM failed WHERE url = ?", (url,))
        conn.execute("INSERT OR REPLACE INTO completed VALUES (?)", (url,))
        conn.commit()
    except _DB_FALLBACK_ERRORS:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
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
        except _DB_FALLBACK_ERRORS:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _load_from_db(self) -> None:
        import heapq
        import sqlite3
        from urllib.parse import urlparse

        # Allocate fresh containers we can swap in atomically on success.
        # If DB load fails midway, we discard these new_* containers and
        # keep the existing in-memory state untouched.
        new_completed: set[str] = set()
        new_failed: dict[str, int] = {}
        new_queue: list[CrawlItem] = []
        new_pending: set[str] = set()
        new_domain_counts: dict[str, int] = {}

        try:
            conn = sqlite3.connect(self._db_path)
            try:
                # Load completed
                for row in conn.execute("SELECT url FROM completed"):
                    url = row[0]
                    new_completed.add(url)
                    domain = urlparse(url).netloc
                    new_domain_counts[domain] = new_domain_counts.get(domain, 0) + 1

                # Load failed
                for row in conn.execute("SELECT url, count FROM failed"):
                    new_failed[row[0]] = row[1]

                # Load queue
                for row in conn.execute("SELECT priority, url, depth, source_url, added_at FROM queue"):
                    if row[1] not in new_completed:
                        item = CrawlItem(priority=row[0], url=row[1], depth=row[2], source_url=row[3], added_at=row[4])
                        new_queue.append(item)
                        new_pending.add(row[1])
            finally:
                conn.close()

            # Heapify to establish priority invariant
            heapq.heapify(new_queue)
        except _DB_FALLBACK_ERRORS:
            # L3: discard the partially-loaded fresh state and keep the
            # pre-call snapshot — frontier stays internally consistent.
            logger.exception("Failed to load frontier state from SQLite")
            return

        # Commit the freshly loaded state atomically.
        self._completed = new_completed
        self._failed = new_failed
        self._queue = new_queue
        self._pending = new_pending
        self._domain_page_counts = new_domain_counts

    async def add_url(self, url: str, priority: int = 10, depth: int = 0, source_url: str | None = None) -> bool:
        """Add a URL to the frontier if it hasn't been crawled yet."""
        if not url or not url.startswith("http"):
            return False

        # M3: perform in-memory mutation under the lock, then release the
        # lock and persist to SQLite outside of it. Holding _lock across
        # ``run_in_threadpool`` serialized concurrent add_url/mark_completed
        # callers behind one another's SQLite I/O. The rollback path on
        # DB write failure still re-acquires the lock briefly to restore
        # in-memory state — concrete failure recovery, not silent drift.
        item_priority = priority + (depth * 5)
        item = CrawlItem(priority=item_priority, url=url, depth=depth, source_url=source_url)
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

            # 2. Priority calculation (lower = higher priority) is already
            # captured above; mutate heap + pending set so dedupe/heap-order
            # invariants remain coherent under the lock.
            heapq.heappush(self._queue, item)
            self._pending.add(url)

        # Outside the lock: persist the new queue row concurrently with
        # other frontier operations.
        try:
            await run_in_threadpool(
                _db_insert_queue,
                self._db_path,
                item.priority,
                url,
                depth,
                source_url,
                item.added_at,
            )
        except _DB_FALLBACK_ERRORS:
            # M5: DB write failed — undo in-memory mutation so
            # frontier doesn't diverge from persistent storage.
            logger.exception("Failed to insert URL into SQLite; reverting in-memory add")
            async with self._lock:
                self._pending.discard(url)
                # Remove from heap (rebuild — heapq has no O(log n) delete)
                self._queue = [it for it in self._queue if it.url != url]
                heapq.heapify(self._queue)

        logger.debug("[Frontier] Added URL: %s (depth: %d, priority: %d)", url, depth, item_priority)
        return True

    async def get_next_url(self) -> str | None:
        """Get the next URL available for crawling, respecting policy."""
        # M3: each frontier operation now does its in-memory mutation under
        # ``self._lock`` and releases the lock before any SQLite I/O so
        # concurrent callers can run their own DB writes in parallel
        # instead of serializing behind one another.
        tried: list[CrawlItem] = []
        max_retries = 1000  # safety valve: prevent unbounded queue scan
        retries = 0

        while retries < max_retries:
            retries += 1
            # 1. Pop a candidate item under the lock; release the lock
            # before the SQLite delete so concurrent frontier ops don't
            # queue behind our threadpool DB I/O.
            popped: CrawlItem | None = None
            async with self._lock:
                if not self._queue:
                    items_to_restore = [item for item in tried if item.url not in self._completed]
                    for item in items_to_restore:
                        heapq.heappush(self._queue, item)
                        self._pending.add(item.url)
                    break  # exits the while — empty queue path below re-acquires to persist

                popped = heapq.heappop(self._queue)
                # Temporarily remove from pending during the policy check.
                self._pending.discard(popped.url)

            # popped is guaranteed populated here (we break'd or popped above)
            if popped is None:  # pragma: no cover
                msg = "Frontier invariant: popped is None after queue pop"
                raise RuntimeError(msg)

            # Outside the lock: persist the queue-row delete concurrently
            # with the policy check (which awaits).
            try:
                await run_in_threadpool(_db_delete_queue, self._db_path, popped.url)
            except _DB_FALLBACK_ERRORS:
                logger.exception("Failed to delete URL from SQLite queue")

            # 2. Evaluate policy check outside the lock — the policy
            # check is a network-touching op we never want holding _lock.
            block_reason = await self._policy.check_domain(popped.url)
            item = popped

            if not block_reason:
                # Eligible: re-mark the URL pending, persist its row, and
                # restore tried items to the heap under a brief lock window.
                pending_restore: list[CrawlItem] = [item, *tried]
                async with self._lock:
                    for it in pending_restore:
                        if it.url not in self._completed:
                            heapq.heappush(self._queue, it)
                            self._pending.add(it.url)

                # Outside the lock: persist all restored rows concurrently.
                for it in pending_restore:
                    if it.url in self._completed:
                        continue
                    try:
                        await run_in_threadpool(
                            _db_insert_queue,
                            self._db_path,
                            it.priority,
                            it.url,
                            it.depth,
                            it.source_url,
                            it.added_at,
                        )
                    except _DB_FALLBACK_ERRORS:
                        logger.exception(
                            "Failed to restore URL to SQLite: %s",
                            it.url,
                        )
                return item.url

            # Blocked by policy: mark the popped URL pending again under
            # the lock, leave the heap alone (queue.pop already removed it),
            # and persist the re-pending state outside the lock.
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
            except _DB_FALLBACK_ERRORS:
                logger.exception("Failed to save blocked URL")
            tried.append(item)

            if len(tried) > 20:  # Don't look too deep
                break

        # 3. Empty-queue path or trailing tried-restore when we ran out of
        # patience. Restore tried items to the heap under the lock, then
        # persist outside.
        items_to_restore = [item for item in tried if item.url not in self._completed]
        if items_to_restore:
            async with self._lock:
                for item in items_to_restore:
                    heapq.heappush(self._queue, item)
                    self._pending.add(item.url)
            for item in items_to_restore:
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
                except _DB_FALLBACK_ERRORS:
                    logger.exception("Failed to restore tried URLs")
        return None

    async def mark_completed(self, url: str, success: bool = True) -> None:
        """Mark a URL as completed or failed."""
        # M3: perform lapped in-memory state mutation under the lock, then
        # release before SQLite I/O to avoid serializing concurrent frontier
        # tasks. Rollback re-acquires the lock on DB failure.
        db_write: tuple[Any, ...]
        async with self._lock:
            if url in self._pending:
                self._pending.remove(url)

            if success:
                self._completed.add(url)
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
                self._domain_page_counts[domain] = self._domain_page_counts.get(domain, 0) + 1
                self._failed.pop(url, None)
                db_write = (_db_mark_completed, url)
            else:
                count = self._failed.get(url, 0) + 1
                self._failed[url] = count
                db_write = (_db_mark_failed, url, count)

                # Retry logic: if not too many failures, put back in queue with
                # lower priority.
                if count < settings.CRAWL_MAX_RETRIES_PER_DOMAIN and url not in self._pending:
                    item = CrawlItem(priority=100 + (count * 20), url=url, depth=0)
                    heapq.heappush(self._queue, item)
                    self._pending.add(url)
                    db_write = (_db_insert_queue, item.priority, url, item.depth, item.source_url, item.added_at)
                else:
                    # Move to completed to stop retrying
                    self._completed.add(url)
                    from urllib.parse import urlparse

                    domain = urlparse(url).netloc
                    self._domain_page_counts[domain] = self._domain_page_counts.get(domain, 0) + 1
                    db_write = (_db_finalize_failed_as_completed, url)

        # Outside the lock: persist the outcome concurrently
        fn, *args = db_write
        try:
            await run_in_threadpool(fn, self._db_path, *args)
        except _DB_FALLBACK_ERRORS:
            logger.exception("Failed to persist completion state to SQLite for %s", url)
            # If we inserted a retry, revert the in-memory mutation on failure
            if fn == _db_insert_queue:
                async with self._lock:
                    self._pending.discard(url)
                    self._queue = [it for it in self._queue if it.url != url]
                    heapq.heapify(self._queue)

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
                    # FU-2026-07-05 (CRIT-4 consistency): if the DB delete
                    # for a popped domain URL fails, restore the URL to the
                    # heap and skip returning it. Otherwise in-memory and
                    # on-disk state diverge: caller thinks the URL is
                    # dequeued, but the DB row resurrects on restart as an
                    # orphan the frontier has "forgotten" about.
                    try:
                        await run_in_threadpool(_db_delete_queue, self._db_path, item.url)
                    except _DB_FALLBACK_ERRORS:
                        logger.exception("Failed to delete domain URL from SQLite; restoring to queue")
                        heapq.heappush(self._queue, item)
                        continue
                    domain_urls.append(item.url)
                    self._pending.discard(item.url)
                else:
                    remaining.append(item)
            # Re-push non-domain items
            for item in remaining:
                heapq.heappush(self._queue, item)
        return domain_urls

    def get_stats(self) -> dict[str, Any]:
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
_frontier_lock = threading.Lock()


def get_crawl_frontier() -> CrawlFrontier:
    global _frontier
    if _frontier is not None:
        return _frontier
    with _frontier_lock:
        if _frontier is not None:
            return _frontier
        _frontier = CrawlFrontier()
    return _frontier
