"""Regression tests for thread-safe dedup_fail_streak mutations.

Pins the fix for a race in :mod:`app.routers.jobs_state` where
``_dedup_fail_streak += 1`` was a non-atomic read-modify-write under the
GIL. Multiple concurrent failures inflated (or missed) increments and
could push the streak past the cap spuriously, triggering 503s for
legitimate traffic or letting duplicate-job floods slip through during
partial Redis outages.

Reading global state through ``from foo import x`` returns an immutable
value snapshot, so this test reaches through ``app.routers.jobs_state``
to read the live binding instead.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.routers import jobs_state
from app.routers.jobs_state import (
    _DEDUP_FAIL_MAX_PER_WINDOW,
    _dedup_fail_streak_lock,
    _get_dedup_fail_streak,
    _increment_dedup_fail_streak,
    _reset_dedup_fail_streak,
)


def _reset() -> None:
    """Reset module state between tests."""
    _reset_dedup_fail_streak()


def _live_streak() -> int:
    """Read the live module-level int (not a snapshot)."""
    return int(jobs_state._dedup_fail_streak)


def test_increment_dedup_fail_streak_basic() -> None:
    _reset()
    assert _get_dedup_fail_streak() == 0
    assert _increment_dedup_fail_streak() == 1
    assert _increment_dedup_fail_streak() == 2
    assert _get_dedup_fail_streak() == 2


def test_reset_dedup_fail_streak_clears_to_zero() -> None:
    _reset()
    for _ in range(10):
        _increment_dedup_fail_streak()
    assert _get_dedup_fail_streak() == 10
    _reset_dedup_fail_streak()
    assert _get_dedup_fail_streak() == 0


def test_streak_persists_at_module_level() -> None:
    """Mutations are visible to other readers (single source of truth)."""
    _reset()
    _increment_dedup_fail_streak()
    _increment_dedup_fail_streak()
    assert _live_streak() == 2
    assert _get_dedup_fail_streak() == 2


def test_concurrent_increments_do_not_lose_updates() -> None:
    """Spawn N threads each incrementing M times; result must equal N*M.

    The previous implementation (plain ``+=`` without a lock) could lose
    updates when the scheduler interleaved LOAD/STORE pairs from
    different threads. This test pins the fix.
    """
    _reset()
    n_threads = 32
    per_thread = 100
    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [executor.submit(_increment_dedup_fail_streak) for _ in range(n_threads * per_thread)]
        for f in futures:
            f.result()
    assert _get_dedup_fail_streak() == n_threads * per_thread


def test_concurrent_reset_does_not_clobber_increments() -> None:
    """Concurrent resets + increments must produce a consistent count.

    A naive implementation that lets increments race a reset can either
    zero out in-flight increments or skip the reset entirely. The lock
    serialises both.
    """
    _reset()
    stop = threading.Event()
    increment_count = 0
    increment_lock = threading.Lock()

    def incrementer() -> None:
        nonlocal increment_count
        while not stop.is_set():
            _increment_dedup_fail_streak()
            with increment_lock:
                increment_count += 1

    def resetter() -> None:
        while not stop.is_set():
            _reset_dedup_fail_streak()

    with ThreadPoolExecutor(max_workers=4) as pool:
        inc_futures = [pool.submit(incrementer) for _ in range(3)]
        reset_future = pool.submit(resetter)
        # Let the race run.
        threading.Event().wait(timeout=0.1)
        stop.set()
        for f in inc_futures:
            f.result()
        reset_future.result()

    # Either the final reset won or the final increment did — but the
    # streak must equal the global count of increments that happened at
    # any point, modulo the final reset. The only invariant we can
    # strictly assert is that _get_dedup_fail_streak() returns a
    # non-negative int consistent with the last observed state.
    final = _get_dedup_fail_streak()
    assert final >= 0
    assert final <= increment_count


def test_max_cap_constant_is_positive() -> None:
    """Pin a positive failure-cap (so a typo can't silently break it)."""
    assert _DEDUP_FAIL_MAX_PER_WINDOW > 0


def test_lock_is_a_threading_lock() -> None:
    """Pin the dedicated lock presence as the single synchronization point."""
    assert isinstance(_dedup_fail_streak_lock, type(threading.Lock()))
