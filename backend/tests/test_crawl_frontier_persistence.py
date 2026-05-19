"""
Unit Tests for SQLite Persistence and Continuity of the Crawl Frontier.
"""

from __future__ import annotations

import os
import sqlite3
import pytest
import asyncio
from app.crawl_frontier import CrawlFrontier, CrawlItem


@pytest.fixture(autouse=True)
def clean_db():
    db_path = "backend/data/crawl_frontier.db"
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass
    yield
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_frontier_persistence_across_restarts():
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
    # page2: 5
    # page1: 10
    # start: 50 + 1 * 5 = 55
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
