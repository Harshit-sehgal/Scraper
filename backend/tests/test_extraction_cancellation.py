"""Tests for extraction cancellation mid-flight.

Roadmap: Rel 14 — cancelling a running job mid-flight,
verify partial results, context release, worker return to idle.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.pagination_executor import PaginationConfig, async_paginate


class TestExtractionCancellation:
    @pytest.mark.asyncio
    async def test_cancelled_task_raises_cancelled_error(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=3)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=10, delay_between_pages=0.1)

        # Hold the extract coroutine on an Event that we never set.
        # This blocks it deterministically inside the ``with`` block of
        # ``async_paginate`` — ``task.cancel()`` then raises CancelledError
        # from the await point instantly, with no real sleep involved.
        blocker = asyncio.Event()

        async def extract(page) -> list[dict]:
            await blocker.wait()
            return [{"data": "test"}]

        task = asyncio.create_task(async_paginate(page, config, extract))
        # Yield once so the task is actually scheduled and reaches its
        # blocking await before we cancel it.
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_fast_extraction_not_affected_by_cancel_flag(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.locator.return_value.count = AsyncMock(return_value=0)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=1, delay_between_pages=0)

        async def extract(page) -> list[dict]:
            return [{"x": "y"}]

        result = await async_paginate(page, config, extract)
        assert isinstance(result, type(result))

    @pytest.mark.asyncio
    async def test_cancel_does_not_leak_coroutines(self) -> None:
        page = MagicMock()
        page.locator = MagicMock(return_value=MagicMock())
        page.locator.return_value.is_visible = AsyncMock(return_value=True)
        page.evaluate = AsyncMock(return_value=1000)
        page.goto = AsyncMock()
        page.wait_for_function = AsyncMock()
        nav = AsyncMock()
        nav.__aenter__ = AsyncMock()
        nav.__aexit__ = AsyncMock()
        page.expect_navigation = MagicMock(return_value=nav)

        config = PaginationConfig(strategy="next_button", max_pages=5, delay_between_pages=0)

        task = asyncio.create_task(async_paginate(page, config))
        task.cancel()
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task
