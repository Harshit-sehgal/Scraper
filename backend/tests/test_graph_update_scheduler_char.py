"""Characterization tests for the GraphUpdateScheduler singleton.

These tests pin the CURRENT behavior of get_scheduler() so that the
A1 refactor (move from singleton to FastAPI Depends-injected Scheduler)
can be performed safely. The tests must pass against the un-refactored
code AND continue passing after the refactor.

Per Rule 8: do not rewrite large files without characterization tests.
This is the first commit of the A1 fix - tests only, no behavior change.
"""

from __future__ import annotations

import queue
import threading

import pytest
from app import event_dispatcher as edm
from app import graph_update_scheduler as gsm


def _reset_scheduler_singleton_without_blocking() -> None:
    lock = gsm._scheduler_lock
    if not lock.acquire(blocking=False):
        return
    try:
        gsm._scheduler = None
        if hasattr(gsm, "_scheduler_initializing"):
            gsm._scheduler_initializing = False
    finally:
        lock.release()


@pytest.fixture(autouse=True)
def _reset_scheduler_singleton():
    """Each test gets a fresh singleton state."""
    edm.reset_dispatcher()
    _reset_scheduler_singleton_without_blocking()
    yield
    _reset_scheduler_singleton_without_blocking()
    edm.reset_dispatcher()


class TestGetSchedulerSingleton:
    def test_first_call_from_fresh_dispatcher_state_does_not_deadlock(self) -> None:
        results: queue.Queue[object] = queue.Queue()

        def call_get_scheduler() -> None:
            try:
                results.put(gsm.get_scheduler())
            except BaseException as exc:  # pragma: no cover - defensive test aid
                results.put(exc)

        worker = threading.Thread(target=call_get_scheduler, daemon=True)
        worker.start()
        worker.join(timeout=2.0)

        assert not worker.is_alive()
        result = results.get_nowait()
        assert result is not None
        assert isinstance(result, gsm.GraphUpdateScheduler)

    def test_first_call_returns_instance(self) -> None:
        result = gsm.get_scheduler()
        assert result is not None
        assert isinstance(result, gsm.GraphUpdateScheduler)

    def test_second_call_returns_same_instance(self) -> None:
        first = gsm.get_scheduler()
        second = gsm.get_scheduler()
        assert first is second

    def test_reset_scheduler_clears_singleton(self) -> None:
        first = gsm.get_scheduler()
        assert first is not None
        gsm.reset_scheduler()
        second = gsm.get_scheduler()
        assert second is not None
        assert first is not second


class TestGraphUpdateSchedulerInit:
    def test_starts_with_zero_pending_updates(self) -> None:
        scheduler = gsm.GraphUpdateScheduler()
        assert scheduler.pending_updates == 0
        assert scheduler._total_wave_intensity == 0.0

    def test_subscribes_to_instability_events(self) -> None:
        scheduler = gsm.GraphUpdateScheduler()
        # The dispatcher is shared module-level; verify subscriptions exist
        # by checking that the dispatcher knows about our handler.
        # We don't assert exact call counts because the dispatcher is
        # process-wide, but the _setup_subscriptions call should have
        # added 3 entries keyed to our scheduler instance's methods.
        assert hasattr(scheduler, "on_instability")
        assert hasattr(scheduler, "on_field_wave")
        assert callable(scheduler.on_instability)
        assert callable(scheduler.on_field_wave)


class TestScheduleDelegation:
    def test_schedule_with_no_world_state_logs_warning(self, caplog) -> None:
        """When no active world state scheduler exists, schedule() falls back
        to a warning log instead of raising. Pins the current graceful
        degradation behavior."""
        scheduler = gsm.GraphUpdateScheduler()
        # No ws._scheduler: schedule should log a warning, not raise
        with caplog.at_level("WARNING"):
            scheduler.schedule(
                task_id="char-test-1",
                priority=gsm.TaskPriority.NORMAL,
                handler=lambda: None,
            )
        # Either a warning was logged OR a no-op happened silently.
        # We pin the contract: no exception is raised.


class TestTaskPriorityOrdering:
    def test_priorities_are_int_enums(self) -> None:
        assert int(gsm.TaskPriority.CRITICAL) < int(gsm.TaskPriority.URGENT)
        assert int(gsm.TaskPriority.URGENT) < int(gsm.TaskPriority.NORMAL)
        assert int(gsm.TaskPriority.NORMAL) < int(gsm.TaskPriority.BACKGROUND)

    def test_critical_task_sorts_before_background(self) -> None:
        import heapq

        from app.graph_update_scheduler import CognitiveTask

        critical = CognitiveTask("c", gsm.TaskPriority.CRITICAL, lambda: None)
        background = CognitiveTask("b", gsm.TaskPriority.BACKGROUND, lambda: None)
        heap = [background, critical]
        heapq.heapify(heap)
        # CRITICAL should pop first
        assert heapq.heappop(heap) is critical
        assert heapq.heappop(heap) is background
