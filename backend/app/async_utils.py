"""Async helpers for running blocking calls without relying on asyncio.to_thread."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


async def run_sync_in_thread(
    func: Callable[..., T],
    *args,
    **kwargs,
) -> T:
    """Run a blocking function in a background thread and await its result.

    Uses asyncio.to_thread when available (Python 3.9+) which is more
    efficient than manual thread polling. Falls back to run_in_executor
    for maximum compatibility.
    """
    loop = asyncio.get_running_loop()

    # Use asyncio.to_thread if available (Python 3.9+) for optimal
    # event-loop integration.
    if hasattr(asyncio, "to_thread"):
        return await asyncio.to_thread(func, *args, **kwargs)

    # Fallback for older runtimes: use run_in_executor with a
    # ThreadPoolExecutor.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))
