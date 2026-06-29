"""Tests for CrawlStateAdapter and its module-level singleton."""

from __future__ import annotations

from app.crawl_state import CrawlStateAdapter, get_crawl_state


class TestCrawlStateAdapter:
    """Tests for CrawlStateAdapter behavior."""

    def test_get_stats_returns_dict_with_expected_keys(self) -> None:
        adapter = CrawlStateAdapter()
        stats = adapter.get_stats()
        assert "frontier" in stats
        assert "policy" in stats


class TestCrawlStateSingleton:
    """Tests for the module-level thread-safe singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        s1 = get_crawl_state()
        s2 = get_crawl_state()
        assert s1 is s2

    def test_singleton_is_crawl_state_adapter(self) -> None:
        s = get_crawl_state()
        assert isinstance(s, CrawlStateAdapter)
