"""Semantic Event Dispatcher.
==========================

Synchronous / Asynchronous propagation of semantic signals.
"""

import logging
import threading
import time
from collections.abc import Callable

from app.semantic_events import SemanticEvent, SemanticEventType

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Central hub for semantic event propagation.

    Engines subscribe to specific event types to react to topological changes.
    Thread-safe: ``subscribe``/``unsubscribe``/``dispatch`` are guarded by
    an internal lock so background threads can register handlers while the
    main event loop dispatches events.
    """

    def __init__(self) -> None:
        self.subscribers: dict[SemanticEventType, list[Callable]] = {t: [] for t in SemanticEventType}
        self._lock = threading.Lock()

    def subscribe(self, event_type: SemanticEventType, callback: Callable) -> None:
        """Register a callback for a specific event type."""
        with self._lock:
            self.subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: SemanticEventType, callback: Callable) -> None:
        """Remove a callback for a specific event type."""
        with self._lock:
            subs = self.subscribers.get(event_type, [])
            if callback in subs:
                subs.remove(callback)

    def dispatch(self, event: SemanticEvent) -> None:
        """Propagate an event to all interested subscribers."""
        event.timestamp = time.time()
        logger.debug(
            "[SEMANTIC EVENT] %s from %s (instability=%.3f)",
            event.event_type.value,
            event.source,
            event.instability_delta,
        )

        # Snapshot subscribers under lock to avoid iteration-during-mutation
        with self._lock:
            callbacks = list(self.subscribers.get(event.event_type, []))

        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.exception("Error in event callback")
                # Record degradation telemetry (best-effort)
                try:
                    from app.semantic_world_state import get_world_state

                    ws = get_world_state()
                    ws.record_degradation(
                        subsystem="event_dispatcher",
                        severity="warning",
                        cause=f"Event callback failed for {event.event_type.value} from {event.source}: {e}",
                    )
                except Exception:
                    logger.debug("Failed to record degradation for event callback failure", exc_info=True)


# Global Dispatcher
_dispatcher = EventDispatcher()
_bootstrap_done = False
_bootstrap_lock = threading.Lock()


def get_dispatcher() -> EventDispatcher:
    global _bootstrap_done
    if _bootstrap_done:
        return _dispatcher
    with _bootstrap_lock:
        if _bootstrap_done:
            return _dispatcher
        # Mark bootstrap done BEFORE the inner call to break the
        # re-entrant cycle: get_dispatcher -> get_scheduler ->
        # GraphUpdateScheduler.__init__ -> get_dispatcher again.
        # Without this, the inner call would block on the same
        # non-reentrant lock that the outer call already holds.
        _bootstrap_done = True
        # Safe: graph_update_scheduler uses lazy singleton creation,
        # so importing the module does NOT trigger __init__ or
        # event_dispatcher import.
        from app.graph_update_scheduler import get_scheduler, is_scheduler_initializing

        scheduler = get_scheduler()
        if scheduler is None and not is_scheduler_initializing():
            _bootstrap_done = False
    return _dispatcher


def reset_dispatcher() -> None:
    """Reset the global dispatcher (for testing)."""
    global _dispatcher, _bootstrap_done
    _dispatcher = EventDispatcher()
    _bootstrap_done = False
