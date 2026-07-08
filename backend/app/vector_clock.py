from typing import Dict, Optional
import copy

class VectorClock:
    """A vector clock for tracking causality in a distributed cognitive substrate.
    
    LAW 11 (Implicit): Distributed truth requires causal ordering.
    No state merge can occur without partial ordering of events.
    """
    def __init__(self, node_id: str, clock: Optional[Dict[str, int]] = None):
        self.node_id = node_id
        self._clock = clock if clock else {node_id: 0}

    def increment(self):
        """Increment the local clock value."""
        self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1

    def update(self, remote_clock: Dict[str, int]):
        """Merge a remote clock into the local clock."""
        for node, value in remote_clock.items():
            self._clock[node] = max(self._clock.get(node, 0), value)
        # Also ensure our own node is in the merged clock
        if self.node_id not in self._clock:
            self._clock[self.node_id] = 0

    def get_clock(self) -> Dict[str, int]:
        return copy.deepcopy(self._clock)

    def compare(self, other: Dict[str, int]) -> str:
        """Compare with another clock to determine causality.
        
        Returns:
            "equal", "ancestor", "descendant", or "concurrent"
        """
        self_newer = False
        other_newer = False
        
        all_nodes = set(self._clock.keys()) | set(other.keys())
        
        for node in all_nodes:
            v_self = self._clock.get(node, 0)
            v_other = other.get(node, 0)
            
            if v_self > v_other:
                self_newer = True
            elif v_other > v_self:
                other_newer = True
                
        if self_newer and other_newer:
            return "concurrent"
        if self_newer:
            # Self has some values > other, and other has NO values > self.
            # So other is an ancestor of self.
            return "ancestor"
        if other_newer:
            # Other has some values > self, and self has NO values > other.
            # So other is a descendant of self.
            return "descendant"
        return "equal"

    def to_dict(self) -> Dict[str, int]:
        return self.get_clock()

    @classmethod
    def from_dict(cls, node_id: str, data: Dict[str, int]) -> 'VectorClock':
        return cls(node_id, copy.deepcopy(data))
