"""Semantic Event Definitions.
===========================

Defines the signals that propagate through the cognition architecture.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SemanticEventType(Enum):
    UNCERTAINTY_SPIKE = "uncertainty_spike"
    TOPOLOGY_SHIFT = "topology_shift"
    EQUILIBRIUM_REACHED = "equilibrium_reached"
    FIELD_WAVE = "field_wave"  # Decentralized propagation wave
    # Emitted when selector quality decays or fails
    SELECTOR_FAILURE = "selector_failure"


@dataclass
class SemanticEvent:
    """A semantic signal propagating through the world state."""

    event_type: SemanticEventType
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    instability_delta: float = 0.0  # How much this event destabilizes the graph
    # To be filled by dispatcher
    timestamp: float = field(default_factory=lambda: 0.0)
