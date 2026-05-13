"""
Semantic Event Dispatcher
==========================
Synchronous/Asynchronous propagation of semantic signals.
"""

import time
import logging
from typing import Callable, Dict, List
from app.semantic_events import SemanticEvent, SemanticEventType

class EventDispatcher:
    """
    Central hub for semantic event propagation.
    Engines subscribe to specific event types to react to topological changes.
    """
    def __init__(self):
        self.subscribers: Dict[SemanticEventType, List[Callable]] = {
            t: [] for t in SemanticEventType
        }

    def subscribe(self, event_type: SemanticEventType, callback: Callable):
        """Register a callback for a specific event type."""
        self.subscribers[event_type].append(callback)

    def dispatch(self, event: SemanticEvent):
        """Propagate an event to all interested subscribers."""
        event.timestamp = time.time()
        logging.getLogger(__name__).debug(
            "[SEMANTIC EVENT] %s from %s (instability=%.3f)",
            event.event_type.value, event.source, event.instability_delta)

        for callback in self.subscribers.get(event.event_type, []):
            try:
                callback(event)
            except Exception as e:
                logging.error(f"Error in event callback: {e}")

# Global Dispatcher
_dispatcher = EventDispatcher()
_bootstrap_done = False

def get_dispatcher() -> EventDispatcher:
    global _bootstrap_done
    if not _bootstrap_done:
        _bootstrap_done = True
        # Safe: graph_update_scheduler uses lazy singleton creation,
        # so importing the module does NOT trigger __init__ or event_dispatcher import.
        from app.graph_update_scheduler import get_scheduler
        get_scheduler()
    return _dispatcher
