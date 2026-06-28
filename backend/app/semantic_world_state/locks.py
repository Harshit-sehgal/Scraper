# mypy: ignore-errors
import asyncio
import logging
import threading
import time
from typing import Any, Self

logger = logging.getLogger(__name__)

_LOCK_ACQUIRE_FAILED = "Failed to acquire NonBlockingRLock within timeout"

# When we're inside a running event loop we never block the thread for
# longer than this single acquire call.  Returning ``False`` quickly is
# the only way to prevent indefinite event-loop starvation from sync
# code running on the loop's own thread - the caller is expected to
# back off and retry, or to use the async API.
_ASYNC_SAFE_BLOCKING_CAP = 0.05  # 50 ms

# Total budget used by async-native callers (expression below).
_DEFAULT_ASYNC_TIMEOUT = 30.0


class NonBlockingRLock:
    """An async-friendly reentrant lock wrapper.

    Prevents event-loop starvation in two ways:

    * Sync callers (the existing API) running on a thread that hosts a
      running event loop have their blocking acquire capped at
      ``_ASYNC_SAFE_BLOCKING_CAP`` seconds.  This protects the loop from
      being stalled indefinitely while waiting for a lock that is held
      by another thread.  Callers that require longer waits should
      switch to the async API (see below) or back off and retry.

    * Async-native callers can use ``acquire_async()`` (or
      ``async with lock:``) which performs short non-blocking
      acquisitions interleaved with ``asyncio.sleep(0)`` to yield to
      the event loop, so other coroutines always make progress while
      waiting.

    The original sync API (``acquire``, ``release``, ``__enter__``,
    ``__exit__``) is preserved unchanged so existing callers do not
    need to be modified.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _in_running_loop() -> bool:
        """Return True if called from the thread that owns a running event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    async def _acquire_async(self, timeout: float) -> bool:
        """Yield-and-retry acquisition for async contexts.

        Instead of blocking the thread (and starving the event loop) we
        perform short non-blocking probes, yielding to the event loop
        between each one so other coroutines can make progress.
        """
        deadline = time.monotonic() + timeout
        while True:
            if self._lock.acquire(blocking=False):
                return True

            # Give other coroutines a chance to run.  ``asyncio.sleep(0)``
            # returns control here after at least one callback cycle,
            # which is more than enough delay for a thread that is about
            # to release the lock to do so.
            await asyncio.sleep(0)

            if time.monotonic() >= deadline:
                return False

    # ------------------------------------------------------------------
    # Public API  (sync-compatible, async-aware)
    # ------------------------------------------------------------------

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if not blocking:
            return self._lock.acquire(blocking=False)

        # If we're inside a running event loop we must not block the
        # thread for an arbitrary time, or we will starve the loop.
        # ``threading.RLock`` does not provide any mechanism to yield to
        # the event loop while waiting, so the only safe option is to
        # return failure quickly.  Async callers should use
        # ``acquire_async`` (or ``async with lock:``) instead, which
        # performs the wait cooperatively.
        if self._in_running_loop():
            return self._lock.acquire(blocking=True, timeout=_ASYNC_SAFE_BLOCKING_CAP)

        # Pure sync path -- no running event loop.
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    async def acquire_async(self, timeout: float = _DEFAULT_ASYNC_TIMEOUT) -> bool:
        """Async-native acquisition that yields to the event loop.

        Callers running inside ``async def`` should prefer this method
        over the synchronous ``acquire``.  It uses ``asyncio.sleep(0)``
        between short non-blocking probes so the event loop stays
        responsive while waiting for the lock.
        """
        return await self._acquire_async(timeout)

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> Self:
        if not self.acquire():
            raise RuntimeError(_LOCK_ACQUIRE_FAILED)
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.release()

    async def __aenter__(self) -> Self:
        if not await self.acquire_async():
            raise RuntimeError(_LOCK_ACQUIRE_FAILED)
        return self

    async def __aexit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.release()
