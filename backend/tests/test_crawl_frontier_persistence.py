"""Unit Tests for SQLite Persistence and Continuity of the Crawl Frontier."""

from __future__ import annotations

import os
import tempfile

import pytest
from app.crawl_frontier import CrawlFrontier


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    from app import crawl_policy
    from app.config import settings
    from app.crawl_frontier import CrawlFrontier

    monkeypatch.setattr(settings, "CRAWL_RESPECT_ROBOTS", False)
    crawl_policy._policy_engine = None

    # Use an isolated temporary database path so this test never collides
    # with other test processes writing to the shared crawl_frontier.db.
    tmp_dir = tempfile.mkdtemp(prefix="crawl_frontier_test_")
    db_path = os.path.join(tmp_dir, "crawl_frontier.db")  # noqa: PTH118

    # Patch _init_db and _load_from_db to override the db_path before
    # they access it. This avoids the instance-attribute-shadows-class-
    # attribute problem with direct monkeypatch.setattr on _db_path.
    original_init_db = CrawlFrontier._init_db

    def patched_init_db(self):
        self._db_path = db_path
        return original_init_db(self)

    monkeypatch.setattr(CrawlFrontier, "_init_db", patched_init_db)

    original_load = CrawlFrontier._load_from_db

    def patched_load(self):
        self._db_path = db_path
        return original_load(self)

    monkeypatch.setattr(CrawlFrontier, "_load_from_db", patched_load)

    yield

    crawl_policy._policy_engine = None
    # Clean up the temp directory
    try:
        for f in os.listdir(tmp_dir):  # noqa: PTH208
            os.remove(os.path.join(tmp_dir, f))  # noqa: PTH107, PTH118
        os.rmdir(tmp_dir)  # noqa: PTH106
    except Exception:  # noqa: RUF100, S110
        pass


@pytest.mark.asyncio
async def test_frontier_persistence_across_restarts() -> None:
    # 1. Start original frontier and add some URLs
    frontier = CrawlFrontier()

    # Verify starting state is empty
    assert len(frontier._queue) == 0
    assert len(frontier._completed) == 0

    # Add URLs
    added1 = await frontier.add_url("https://example.com/page1", priority=10, depth=0)
    added2 = await frontier.add_url("https://example.com/page2", priority=5, depth=0)
    added3 = await frontier.add_url("https://another.com/start", priority=50, depth=1)

    assert added1 is True
    assert added2 is True
    assert added3 is True
    assert len(frontier._queue) == 3
    assert "https://example.com/page1" in frontier._pending

    # 2. Pop the highest priority URL (priority 5 + depth 0 * 5 = 5)
    # The priorities will be:
    # page2: 5  # noqa: ERA001
    # page1: 10  # noqa: ERA001
    # start: 50 + 1 * 5 = 55  # noqa: ERA001
    next_url = await frontier.get_next_url()
    assert next_url == "https://example.com/page2"

    # Since it is popped, it is active and deleted from the persistent queue table
    assert len(frontier._queue) == 2

    # Mark it as completed
    await frontier.mark_completed("https://example.com/page2", success=True)
    assert "https://example.com/page2" in frontier._completed

    # 3. Simulate process restart by instantiating a completely fresh CrawlFrontier
    new_frontier = CrawlFrontier()

    # Assert that the state was correctly loaded from the SQLite database
    assert "https://example.com/page2" in new_frontier._completed
    assert "https://example.com/page2" not in new_frontier._pending

    assert len(new_frontier._queue) == 2
    assert "https://example.com/page1" in new_frontier._pending
    assert "https://another.com/start" in new_frontier._pending

    # Verify that the loaded queue is heapified and yields page1 first (priority 10) before start (priority 55)
    first_popped = await new_frontier.get_next_url()
    assert first_popped == "https://example.com/page1"

    second_popped = await new_frontier.get_next_url()
    assert second_popped == "https://another.com/start"

    # No more URLs
    assert await new_frontier.get_next_url() is None


@pytest.mark.asyncio
async def test_domain_crawl_limit() -> None:
    from app.config import settings

    # Override settings limit for testing
    original_limit = settings.CRAWL_MAX_PAGES_PER_DOMAIN
    settings.CRAWL_MAX_PAGES_PER_DOMAIN = 2

    try:
        frontier = CrawlFrontier()

        # Add 2 URLs for the same domain
        assert await frontier.add_url("https://cap.com/page1") is True
        assert await frontier.add_url("https://cap.com/page2") is True

        # Get next URL, mark completed to increment domain crawl count
        url1 = await frontier.get_next_url()
        assert url1 is not None
        await frontier.mark_completed(url1, success=True)

        url2 = await frontier.get_next_url()
        assert url2 is not None
        await frontier.mark_completed(url2, success=True)

        # Verify that domain capillary count is 2
        assert frontier._domain_page_counts.get("cap.com") == 2

        # Try adding page3 for cap.com -> should be rejected because limit is 2
        assert await frontier.add_url("https://cap.com/page3") is False

        # Test that restart preserves counts
        new_frontier = CrawlFrontier()
        assert new_frontier._domain_page_counts.get("cap.com") == 2
        assert await new_frontier.add_url("https://cap.com/page3") is False

    finally:
        settings.CRAWL_MAX_PAGES_PER_DOMAIN = original_limit
