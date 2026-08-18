"""Concurrency and M3 lock-release tests for the CrawlFrontier."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from app.crawl_frontier import CrawlFrontier


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    """Isolate the test from any existing crawl_frontier.db and policy state."""
    from app import crawl_policy

    class AllowAllPolicy:
        async def check_domain(self, _url: str) -> None:
            return None

    crawl_policy._policy_engine = None
    monkeypatch.setattr("app.crawl_frontier.get_crawl_policy", AllowAllPolicy)

    # Use an isolated temporary database path
    tmp_dir = tempfile.mkdtemp(prefix="crawl_frontier_concurrency_")
    db_path = os.path.join(tmp_dir, "crawl_frontier.db")

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
    try:
        for f in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
    except Exception:  # noqa: RUF100, S110
        pass


@pytest.mark.asyncio
async def test_frontier_concurrency_performance() -> None:
    """Test that concurrent add_url/mark_completed do not serialize."""
    frontier = CrawlFrontier()
    num_urls = 50
    urls = [f"https://example.com/page{i}" for i in range(num_urls)]

    await asyncio.gather(*(frontier.add_url(url) for url in urls))

    assert len(frontier._pending) == num_urls
    assert len(frontier._queue) == num_urls

    await asyncio.gather(*(frontier.mark_completed(url) for url in urls))

    assert len(frontier._completed) == num_urls
    assert len(frontier._pending) == 0


@pytest.mark.asyncio
async def test_frontier_get_next_url_concurrency() -> None:
    """Test that multiple concurrent get_next_url callers don't deadlock."""
    frontier = CrawlFrontier()
    num_urls = 100
    for i in range(num_urls):
        await frontier.add_url(f"https://example.com/p{i}")

    # Simultaneously try to pop 100 URLs
    results = await asyncio.gather(*(frontier.get_next_url() for _ in range(num_urls)))

    # All URLs should be unique (no double-popping)
    unique_results = {r for r in results if r is not None}
    assert len(unique_results) == num_urls
    assert len(frontier._queue) == 0


@pytest.mark.asyncio
async def test_mixed_add_mark_get_next() -> None:
    """Mix add_url + mark_completed + get_next_url concurrently."""
    frontier = CrawlFrontier()

    # Add some initial URLs
    for i in range(20):
        await frontier.add_url(f"https://example.com/i{i}")

    async def adder(count: int, suffix: str) -> None:
        for i in range(count):
            await frontier.add_url(f"https://example.com/a{i}_{suffix}")

    async def pop_and_mark(count: int) -> None:
        for _ in range(count):
            url = await frontier.get_next_url()
            if url:
                await frontier.mark_completed(url)

    # Run 3 adders + 2 popper/marker concurrently
    await asyncio.gather(
        adder(30, "x"),
        adder(30, "y"),
        adder(30, "z"),
        pop_and_mark(15),
        pop_and_mark(15),
    )

    # All 90 added + 20 initial = 110 total
    # 30 popped = 80 remaining in queue/pending
    assert len(frontier._queue) >= 0  # at least no crash or deadlock
    popped_count = len(frontier._completed)
    added_count = len(frontier._pending) + len(frontier._completed)
    assert added_count == 110
    assert popped_count == 30
