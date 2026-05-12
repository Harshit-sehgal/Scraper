"""Async helpers for running blocking calls without relying on asyncio.to_thread."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_sync_in_thread(
    func: Callable[..., T],
    *args,
    poll_interval: float = 0.01,
    **kwargs,
) -> T:
    """
    Run a blocking function in a daemon thread and await its result.

    Some restricted runtimes can fail to wake the event loop from
    asyncio.to_thread/run_in_executor even after the worker returns. Polling a
    completion event avoids that hang while still moving blocking I/O off the
    request loop.
    """
    done = threading.Event()
    result: dict[str, object] = {}

    def _worker() -> None:
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as exc:
            logging.exception(exc)
            result["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()

    while not done.is_set():
        await asyncio.sleep(poll_interval)

    if "error" in result and isinstance(result["error"], BaseException):
        raise result["error"]

    return result.get("value")  # type: ignore[return-value]
