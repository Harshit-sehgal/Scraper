from __future__ import annotations

import copy


class VectorClock:
    """A vector clock for tracking causality in a distributed cognitive substrate.

    LAW 11 (Implicit): Distributed truth requires causal ordering.
    No state merge can occur without partial ordering of events.
    """

    def __init__(self, node_id: str, clock: dict[str, int] | None = None) -> None:
        self.node_id = node_id
        self._clock = clock or {node_id: 0}

    def increment(self) -> None:
        """Increment the local clock value."""
        self._clock[self.node_id] = self._clock.get(self.node_id, 0) + 1

    @property
    def clock(self) -> dict[str, int]:
        """Read-only access to the internal clock dict."""
        return self._clock

    def update(self, remote_clock: dict[str, int]) -> None:
        """Merge a remote clock into the local clock."""
        for node, value in remote_clock.items():
            self._clock[node] = max(self._clock.get(node, 0), value)
        # Also ensure our own node is in the merged clock
        if self.node_id not in self._clock:
            self._clock[self.node_id] = 0

    def get_clock(self) -> dict[str, int]:
        return copy.deepcopy(self._clock)

    def compare(self, other: dict[str, int] | VectorClock) -> str:
        """Compare with another clock to determine causality.

        Args:
            other: A dict mapping node IDs to clock values, or a VectorClock
                instance (its internal clock dict is used).

        Returns:
            "equal", "ancestor", "descendant", or "concurrent"

        """
        other_clock = other._clock if isinstance(other, VectorClock) else other

        self_newer = False
        other_newer = False

        all_nodes = set(self._clock.keys()) | set(other_clock.keys())

        for node in all_nodes:
            v_self = self._clock.get(node, 0)
            v_other = other_clock.get(node, 0)

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

    def to_dict(self) -> dict[str, int]:
        return self.get_clock()

    @classmethod
    def from_dict(cls, node_id: str, data: dict[str, int]) -> VectorClock:
        return cls(node_id, copy.deepcopy(data))
