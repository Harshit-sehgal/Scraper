"""Semantic Event Dispatcher.
==========================
Synchronous / Asynchronous propagation of semantic signals.
"""

import logging
import time
from collections.abc import Callable

from app.semantic_events import SemanticEvent, SemanticEventType

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Central hub for semantic event propagation.
    Engines subscribe to specific event types to react to topological changes.
    """

    def __init__(self) -> None:
        self.subscribers: dict[SemanticEventType, list[Callable]] = {t: [] for t in SemanticEventType}

    def subscribe(self, event_type: SemanticEventType, callback: Callable) -> None:
        """Register a callback for a specific event type."""
        self.subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: SemanticEventType, callback: Callable) -> None:
        """Remove a callback for a specific event type."""
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

        for callback in self.subscribers.get(event.event_type, []):
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
                except Exception:  # nosec B110  # noqa: RUF100, S110
                    pass  # nosec B110


# Global Dispatcher
_dispatcher = EventDispatcher()
_bootstrap_done = False


def get_dispatcher() -> EventDispatcher:
    global _bootstrap_done
    if not _bootstrap_done:
        # Safe: graph_update_scheduler uses lazy singleton creation,
        # so importing the module does NOT trigger __init__ or event_dispatcher
        # import.
        from app.graph_update_scheduler import get_scheduler

        get_scheduler()
        _bootstrap_done = True
    return _dispatcher


def reset_dispatcher() -> None:
    """Reset the global dispatcher (for testing)."""
    global _dispatcher, _bootstrap_done
    _dispatcher = EventDispatcher()
    _bootstrap_done = False
