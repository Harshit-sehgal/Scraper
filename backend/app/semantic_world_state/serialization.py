# mypy: ignore-errors
# type: ignore
import time
from typing import Any

from app.invariant_firewall import requires_invariants


class SerializationMixin:
    def to_dict(self) -> dict[str, Any]:
        """Serialize state to a JSON-compatible dictionary."""
        with self._lock:
            history_journal = self._history.transaction_journal
            last_trace = history_journal[-1].get("trace_id") if history_journal else None
            result = {
                "version": "5.0",
                "last_update": self.last_update_time,
                "node_id": self.node_id,
                "clock": self._vector_clock.to_dict(),
                "last_trace_id": last_trace,
                "parent_node_id": self._parent_node_id,
                "branch_label": self._branch_label,
            }
            result.update(self._energy.to_dict())
            result.update(self._manifold.to_dict())
            result.update(self._motif.to_dict())
            result.update(self._transition.to_dict())
            result["history"] = self._history.to_dict()
            result.update(self._instability.to_dict())
            result.update(self._intent.to_dict())
            result.update(self._action.to_dict())
            result.update(self._abstraction.to_dict())
            result.update(self._observability.to_dict())
            result["topology"] = self._topology.to_dict()
            result["evolved_schema"] = list(self._evolved_schema)
            return result

    @requires_invariants
    def from_dict(self, data: dict[str, Any]) -> None:
        """Load state from a dictionary."""
        self.clear()

        # Load identity
        self.node_id = data.get("node_id", self.node_id)
        self._parent_node_id = data.get("parent_node_id")
        self._branch_label = data.get("branch_label")

        if "clock" in data:
            from app.vector_clock import VectorClock

            self._vector_clock = VectorClock.from_dict(self.node_id, data["clock"])

        # Load EnergyState (supports nested and flat)
        metrics_data = data.get("metrics")
        if metrics_data is not None:
            self._energy.from_dict(metrics_data)
        else:
            metric_keys = {
                "global_energy",
                "global_entropy",
                "exclusion_count",
                "total_records_processed",
                "cumulative_density",
                "cumulative_uncertainty",
                "dataset_coherence",
                "_convergence",
                "_temperature",
                "_integrity",
                "stability_debt",
                "schema_instability",
            }
            flat_metrics = {k: v for k, v in data.items() if k in metric_keys}
            if flat_metrics:
                self._energy.from_dict(flat_metrics)

        self._manifold.from_dict(data)
        self._motif.from_dict(data)
        self._transition.from_dict(data)
        self._history.from_dict(data)
        self._intent.from_dict(data)
        self._action.from_dict(data)
        self._abstraction.from_dict(data)
        self._observability.from_dict(data)

        # Load InstabilityState (learned_exclusions)
        excl_data = data.get("learned_exclusions")
        if excl_data:
            self._instability.from_dict(excl_data)

        # Load TopologyState
        topo_data = data.get("topology")
        if topo_data:
            self._topology.from_dict(topo_data)

        self._evolved_schema = set(data.get("evolved_schema", []))
        self.last_update_time = data.get("last_update", time.time())
        self._last_trace_id = data.get("last_trace_id")
