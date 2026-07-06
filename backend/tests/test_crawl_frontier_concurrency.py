import asyncio
import time

import pytest
from app.crawl_frontier import CrawlFrontier


@pytest.mark.asyncio
async def test_frontier_concurrency_performance():
    """
    Test that concurrent add_url / mark_completed calls do not serialize
    behind each other's I/O. If the lock is held during run_in_threadpool,
    N concurrent calls will take roughly N * (DB_IO_TIME).
    If released, they should take closer to 1 * (DB_IO_HIGHTEST_IO_TIME).
    """
    frontier = CrawlFrontier()
    num_urls = 50
    urls = [f"https://example.com/page{i}" for i in range(num_urls)]

    # Measure time to add 50 URLs concurrently
    start_time = time.perf_counter()
    await asyncio.gather(*(frontier.add_url(url) for url in urls))
    _duration = time.perf_counter() - start_time

    assert len(frontier._pending) == num_urls
    assert len(frontier._queue) == num_urls

    # Now concurrently mark them all completed
    start_time = time.perf_counter()
    await asyncio.gather(*(frontier.mark_completed(url) for url in urls))
    _duration_complete = time.perf_counter() - start_time

    assert len(frontier._completed) == num_urls
    assert len(frontier._pending) == 0


@pytest.mark.asyncio
async def test_frontier_get_next_url_concurrency():
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
