"""Global Cognitive Scheduler — orchestrates field tasks across shards.

LAW 13: Cognitive resources are finite. Tasks must be scheduled based on
field pressure, task priority, and real-time urgency.
"""

import heapq
import logging
import time
from collections import Counter
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEvent, SemanticEventType
from app.semantic_world_state import get_world_state


class TaskPriority(IntEnum):
    CRITICAL = 0
    URGENT = 1
    NORMAL = 2
    BACKGROUND = 3


class CognitiveTask:
    def __init__(
        self,
        task_id: str,
        priority: TaskPriority,
        handler: Callable,
        args: Optional[tuple] = None,
        kwargs: Optional[dict] = None,
    ):
        self.task_id = task_id
        self.priority = priority
        self.handler = handler
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.created_at = time.time()

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at


class GlobalCognitiveScheduler:
    def __init__(self, ws: Any = None) -> None:
        self.ws = ws
        self._task_queue: List[CognitiveTask] = []
        self._is_paused = False
        self._preemption_threshold = 1.8
        self._execution_stats: Dict[str, Any] = {
            "tasks_completed": 0,
            "total_execution_time": 0.0,
            "priority_counts": Counter(),
        }

    def schedule(self, task_id: str, priority: TaskPriority, handler: Callable, *args: Any, **kwargs: Any) -> None:
        task = CognitiveTask(task_id, priority, handler, args, kwargs)
        heapq.heappush(self._task_queue, task)
        logging.getLogger(__name__).debug(f"TASK SCHEDULED: [{task_id}] Priority: {priority.name}")

    def step(self, budget_ms: float = 100.0) -> int:
        if self._is_paused:
            return 0

        # Phase 68: Active Governance Enforcement (Even if queue is empty)
        from app.policy_engine import get_policy_engine

        policy = get_policy_engine(ws=self.ws)
        policy.enforce_guardrails()

        if not self._task_queue:
            return 0

        start_time = time.time()
        completed = 0

        while self._task_queue:
            if (time.time() - start_time) * 1000 >= budget_ms:
                break

            task = heapq.heappop(self._task_queue)

            try:
                pressure = self.ws.get_system_pressure()
            except AttributeError:
                pressure = 1.0

            if pressure > self._preemption_threshold and task.priority > TaskPriority.URGENT:
                heapq.heappush(self._task_queue, task)
                break

            t0 = time.time()
            try:
                task.handler(*task.args, **task.kwargs)
                self._execution_stats["tasks_completed"] += 1
                self._execution_stats["priority_counts"][task.priority.name] += 1
            except Exception as e:
                logging.getLogger(__name__).error(f"TASK FAILED: [{task.task_id}] - {e}")
                # Record degradation telemetry (best-effort)
                try:
                    if hasattr(self, "ws") and self.ws is not None:
                        self.ws.record_degradation(
                            subsystem="cognitive_scheduler",
                            severity="warning",
                            cause=f"Task [{task.task_id}] failed: {e}",
                        )
                except Exception:
                    pass

            duration = time.time() - t0
            self._execution_stats["total_execution_time"] += duration
            completed += 1

        return completed

    def clear(self) -> None:
        self._task_queue.clear()


# Legacy scheduler — kept for backward compatibility


class GraphUpdateScheduler:
    def __init__(self) -> None:
        self.pending_updates: int = 0
        self._total_wave_intensity: float = 0.0
        self.dispatcher = get_dispatcher()
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        self.dispatcher.subscribe(SemanticEventType.UNCERTAINTY_SPIKE, self.on_instability)
        self.dispatcher.subscribe(SemanticEventType.TOPOLOGY_SHIFT, self.on_instability)
        self.dispatcher.subscribe(SemanticEventType.FIELD_WAVE, self.on_field_wave)

    def on_instability(self, event: SemanticEvent) -> None:
        ws = get_world_state()
        ws.record_decision(
            {
                "type": event.event_type.value,
                "source": event.source,
                "delta": event.instability_delta,
                "timestamp": event.timestamp or 0,
            }
        )
        ws.trim_decision_history()

        # Phase 71: Uncertainty spike now triggers a field wave from the source
        # instead of a fixed relaxation wave count.
        if event.event_type == SemanticEventType.UNCERTAINTY_SPIKE:
            source_id = event.payload.get("region_id")
            if source_id:
                ws._topology.emit_field_wave(source_id, event.instability_delta * 2.0)

    def on_field_wave(self, event: SemanticEvent) -> None:
        """Monitor field waves to trigger global manifold relaxation."""
        intensity = event.payload.get("intensity", 0.0)
        self._total_wave_intensity += intensity

        # If total field agitation is high, trigger a manifold relaxation pass
        if self._total_wave_intensity > 2.0:
            self.run_global_relaxation()
            self._total_wave_intensity *= 0.5  # Dampen after work

    def run_global_relaxation(self) -> None:
        """Global manifold relaxation triggered by field agitation."""
        from app.semantic_inference_engine import RoleEmbeddingEngine

        ie = RoleEmbeddingEngine()
        ws = get_world_state()

        pressure_before = ws.metrics.field_pressure
        ie.relax_manifold()
        pressure_after = ws.metrics.field_pressure

        ws.snapshot(label=f"global_relaxation_agitation_{
            round(
                    self._total_wave_intensity,
                    2)}")

        self.dispatcher.dispatch(
            SemanticEvent(
                event_type=SemanticEventType.EQUILIBRIUM_REACHED,
                source="global_relaxation",
                payload={
                    "energy": ws.metrics.global_energy,
                    "agitation": self._total_wave_intensity,
                    "pressure_drop": pressure_before - pressure_after,
                },
                instability_delta=-0.05,
            )
        )

    def schedule(self, task_id: str, priority: TaskPriority, handler: Callable, *args: Any, **kwargs: Any) -> None:
        """Delegate scheduling to the active world state's scheduler."""
        ws = get_world_state()
        if hasattr(ws, "_scheduler") and ws._scheduler:
            ws._scheduler.schedule(task_id, priority, handler, *args, **kwargs)
        else:
            # Fallback for bootstrap / tests
            logging.getLogger(__name__).warning(f"No active scheduler for task {task_id}")


_scheduler: Any = None


def get_scheduler() -> GraphUpdateScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = object()
        _scheduler = GraphUpdateScheduler()
    return _scheduler


def reset_scheduler() -> None:
    """Reset the global scheduler (for testing)."""
    global _scheduler
    _scheduler = None
