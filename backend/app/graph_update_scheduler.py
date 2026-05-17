"""Global Cognitive Scheduler — orchestrates field tasks across shards.

LAW 13: Cognitive resources are finite. Tasks must be scheduled based on
field pressure, task priority, and real-time urgency.
"""

import heapq
import time
import logging
from collections import Counter
from enum import IntEnum
from typing import Dict, List, Optional, Callable, Any


class TaskPriority(IntEnum):
    CRITICAL = 0
    URGENT = 1
    NORMAL = 2
    BACKGROUND = 3


class CognitiveTask:
    def __init__(self, task_id: str, priority: TaskPriority,
                 handler: Callable, args: Optional[tuple] = None, kwargs: Optional[dict] = None):
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
    def __init__(self, ws=None):
        self.ws = ws
        self._task_queue: List[CognitiveTask] = []
        self._is_paused = False
        self._preemption_threshold = 1.8
        self._execution_stats: Dict[str, Any] = {
            "tasks_completed": 0,
            "total_execution_time": 0.0,
            "priority_counts": Counter(),
        }

    def schedule(self, task_id: str, priority: TaskPriority,
                 handler: Callable, *args, **kwargs):
        task = CognitiveTask(task_id, priority, handler, args, kwargs)
        heapq.heappush(self._task_queue, task)
        logging.getLogger(__name__).debug(
            f"TASK SCHEDULED: [{task_id}] Priority: {priority.name}"
        )

    def step(self, budget_ms: float = 100.0) -> int:
        if self._is_paused or not self._task_queue:
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
                logging.getLogger(__name__).error(
                    f"TASK FAILED: [{task.task_id}] - {e}"
                )

            duration = time.time() - t0
            self._execution_stats["total_execution_time"] += duration
            completed += 1

        return completed

    def clear(self):
        self._task_queue.clear()


# Legacy scheduler — kept for backward compatibility
from app.semantic_events import SemanticEvent, SemanticEventType
from app.event_dispatcher import get_dispatcher
from app.semantic_world_state import get_world_state


class GraphUpdateScheduler:
    def _setup_subscriptions(self):
        self.dispatcher.subscribe(SemanticEventType.UNCERTAINTY_SPIKE, self.on_instability)
        self.dispatcher.subscribe(SemanticEventType.TOPOLOGY_SHIFT, self.on_instability)

    def on_instability(self, event: SemanticEvent):
        ws = get_world_state()
        ws.record_decision({
            "type": event.event_type.value,
            "source": event.source,
            "delta": event.instability_delta,
            "timestamp": event.timestamp or 0,
        })
        ws.trim_decision_history()
        self.run_relaxation_pass()

    def __init__(self):
        self.pending_updates = 0
        self._wave_count = 0
        self.dispatcher = get_dispatcher()
        self._setup_subscriptions()

    def run_relaxation_pass(self):
        from app.semantic_inference_engine import RoleEmbeddingEngine
        from app.semantic_ir import SemanticToken, Span, SemanticType

        if self._wave_count >= 3:
            self._wave_count = 0
            return
        self._wave_count += 1

        ie = RoleEmbeddingEngine()
        ws = get_world_state()
        pressure_before = ws.metrics.field_pressure

        virtual_tokens = []
        for (role, ttype), compat in list(ws.role_compatibility.items()):
            if compat > 0.0:
                stype = SemanticType(ttype) if isinstance(ttype, str) else ttype
                virtual_tokens.append(SemanticToken(
                    raw=role, normalized=role, span=Span(0, 0), position=0,
                    primary_type=stype,
                    type_distribution={stype: compat}
                ))

        if virtual_tokens:
            result = ie.infer(virtual_tokens, list(ws.role_position_memory.keys()))
            regions = ws.field_regions
            if regions:
                ws.set_region_energy(regions[-1].region_id, result.energy)

            ws.decay_field_regions()
            ws.aggregate_from_regions()
            ws.redistribute_instability()

            pressure_after = ws.metrics.field_pressure
            drop = pressure_before - pressure_after
            ws.snapshot(label=f"relax_wave_{self._wave_count}")

            self.dispatcher.dispatch(SemanticEvent(
                event_type=SemanticEventType.EQUILIBRIUM_REACHED,
                source="graph_update_scheduler",
                payload={"energy": result.energy, "wave": self._wave_count, "pressure_drop": drop},
                instability_delta=-0.1
            ))

            convergence = ws.metrics.convergence_score
            if drop < 0.02 and pressure_before > 0.3 and self._wave_count < 3 and convergence < 0.8:
                self.dispatcher.dispatch(SemanticEvent(
                    event_type=SemanticEventType.TOPOLOGY_SHIFT,
                    source=f"propagation_wave_{self._wave_count}",
                    payload={"wave": self._wave_count, "pressure": pressure_after},
                    instability_delta=0.05
                ))


_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = object()
        _scheduler = GraphUpdateScheduler()
    return _scheduler
