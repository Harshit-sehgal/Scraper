# mypy: ignore-errors
import threading
from typing import Any

_LOCK_ACQUIRE_FAILED = "Failed to acquire NonBlockingRLock within timeout"


class NonBlockingRLock:
    """An async-friendly reentrant lock wrapper.

    Prevents event-loop starvation by using non-blocking timeout acquisitions
    when called inside a running asyncio event loop, falling back to a standard
    reentrant lock otherwise.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if blocking and timeout < 0:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    # We are in a running event loop thread! Cap blocking wait
                    # to prevent event-loop lockups if another thread holds the
                    # lock.
                    return self._lock.acquire(blocking=True, timeout=1.0)
            except RuntimeError:
                pass  # nosec B110
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> "NonBlockingRLock":
        if not self.acquire():
            raise RuntimeError(_LOCK_ACQUIRE_FAILED)
        return self

    def __exit__(self, _exc_type: Any, _exc_val: Any, _exc_tb: Any) -> None:
        self.release()
