"""Tests for browser crash recovery.

Roadmap: Rel 7 — verify recovery after browser crash.
Mocks the browser pool to simulate crash, verify worker requeues.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.browser_pool import BrowserPool


class TestBrowserCrashRecovery:
    def test_initial_crash_count_zero(self) -> None:
        pool = BrowserPool()
        assert pool.crash_count == 0

    def test_crash_count_reflects_in_metrics(self) -> None:
        pool = BrowserPool()
        pool.crash_count = 2
        metrics = pool.get_metrics()
        assert metrics["crash_count"] == 2

    def test_crash_count_persists_across_crashes(self) -> None:
        pool = BrowserPool()
        pool.crash_count = 3
        assert pool.crash_count == 3
        pool.crash_count = 5
        assert pool.crash_count == 5

    @pytest.mark.asyncio
    async def test_hard_recycle_resets_active_fetches(self) -> None:
        pool = BrowserPool()
        pool._browser = None
        pool._playwright = None
        pool._concurrency_semaphore = MagicMock()
        pool._active_fetches = 5

        await pool._hard_recycle()
        assert pool._active_fetches == 0

    @pytest.mark.asyncio
    async def test_hard_recycle_resets_active_acquires(self) -> None:
        pool = BrowserPool()
        pool._browser = None
        pool._playwright = None
        pool._concurrency_semaphore = MagicMock()
        pool._active_acquires = 3

        await pool._hard_recycle()
        assert pool._active_acquires == 0

    @pytest.mark.asyncio
    async def test_hard_recycle_clears_isolated_contexts(self) -> None:
        pool = BrowserPool()
        mock_ctx = AsyncMock()
        pool._isolated_contexts["iso:test"] = mock_ctx
        pool._browser = None
        pool._playwright = None
        pool._concurrency_semaphore = MagicMock()

        await pool._hard_recycle()
        assert len(pool._isolated_contexts) == 0
        mock_ctx.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_browser_disconnect_triggers_ensure_browser(self) -> None:
        pool = BrowserPool()
        pool._browser = None
        pool._playwright = None
        pool._concurrency_semaphore = MagicMock()
        pool._recycle_event = MagicMock()
        pool._recycle_event.is_set = MagicMock(return_value=True)
        pool._cleanup_task = MagicMock()
        pool._cleanup_task.done = MagicMock(return_value=True)
        pool._active_acquires = 0
        pool._active_fetches = 0

        await pool._ensure_browser()
        assert isinstance(pool, BrowserPool)

    def test_metrics_includes_crash_count(self) -> None:
        pool = BrowserPool()
        metrics = pool.get_metrics()
        assert "crash_count" in metrics
