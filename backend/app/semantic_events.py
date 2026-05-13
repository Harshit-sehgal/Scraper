"""
Semantic Event Definitions
===========================
Defines the signals that propagate through the cognition architecture.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SemanticEventType(Enum):
    BOUNDARY_INSTABILITY = "boundary_instability"
    CONTRADICTION_DETECTED = "contradiction_detected"
    UNCERTAINTY_SPIKE = "uncertainty_spike"
    TOPOLOGY_SHIFT = "topology_shift"
    EQUILIBRIUM_REACHED = "equilibrium_reached"
    MEMORY_REINFORCED = "memory_reinforced"


@dataclass
class SemanticEvent:
    """A semantic signal propagating through the world state."""
    event_type: SemanticEventType
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    instability_delta: float = 0.0 # How much this event destabilizes the graph
    timestamp: float = field(default_factory=lambda: 0.0) # To be filled by dispatcher
