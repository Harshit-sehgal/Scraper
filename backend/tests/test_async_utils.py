"""Tests for app.async_utils — run_sync_in_thread."""

from __future__ import annotations

import pytest
from app.async_utils import run_sync_in_thread


def _sync_add(a: int, b: int) -> int:
    return a + b


def _sync_raises() -> None:
    msg = "sync error"
    raise ValueError(msg)


async def _async_helper() -> int:
    return 42


class TestRunSyncInThread:
    @pytest.mark.asyncio
    async def test_basic_sync_call(self) -> None:
        result = await run_sync_in_thread(_sync_add, 2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_with_kwargs(self) -> None:
        result = await run_sync_in_thread(_sync_add, a=10, b=20)
        assert result == 30

    @pytest.mark.asyncio
    async def test_raises_exception(self) -> None:
        with pytest.raises(ValueError, match="sync error"):
            await run_sync_in_thread(_sync_raises)

    @pytest.mark.asyncio
    async def test_lambda(self) -> None:
        result = await run_sync_in_thread(lambda: 99)
        assert result == 99

    @pytest.mark.asyncio
    async def test_str_method(self) -> None:
        result = await run_sync_in_thread(" hello ".strip)
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_none_return(self) -> None:
        result = await run_sync_in_thread(lambda: None)
        assert result is None
