"""Cognitive Observability — owns field-native telemetry and heatmap data.

True ownership boundary: NO external code should mutate telemetry_stream directly.
All changes go through this state object, which supports transactions.
"""

import time
from typing import Dict, List, Optional, Callable

from collections import deque

class ObservabilityState:
    """Sole owner of the semantic field's telemetry and activity heatmaps."""

    def __init__(self, delta_callback: Optional[Callable[[str, str, dict], None]] = None):
        self._delta_callback = delta_callback
        # Telemetry Stream: recent cognitive events (Ring buffer)
        self._telemetry_stream: deque = deque(maxlen=1000)
        # Regional Heatmaps: region_id -> activity_score
        self._activity_heatmap: Dict[str, float] = {}
        # Manifold Drift Log: role -> [drift_values]
        self._drift_log: Dict[str, deque] = {}
        
        # ─── Transaction Staging ──────────────────────────────────────
        self._staging: Optional[dict] = None

    def _record(self, action: str, details: dict):
        if self._delta_callback:
            self._delta_callback("observability", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self):
        """Snapshot current state for staging."""
        self._staging = {
            "activity_heatmap": dict(self._activity_heatmap),
            "drift_log": {k: deque(v, maxlen=100) for k, v in self._drift_log.items()},
            "telemetry_stream": list(self._telemetry_stream),
        }

    def commit(self):
        """Apply staged changes."""
        if self._staging is not None:
            self._activity_heatmap = self._staging["activity_heatmap"]
            self._drift_log = self._staging["drift_log"]
            self._telemetry_stream = deque(self._staging.get("telemetry_stream", self._telemetry_stream), maxlen=1000)
            self._staging = None

    def rollback(self):
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "activity_heatmap": "_activity_heatmap",
            "drift_log": "_drift_log"
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val):
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "activity_heatmap": "_activity_heatmap",
                "drift_log": "_drift_log"
            }
            setattr(self, attr_map[key], val)

    # ─── Controlled Mutations ────────────────────────────────────────────

    def emit_telemetry(self, event_type: str, details: dict):
        """Record a cognitive event in the telemetry stream (Phase 41)."""
        entry = {
            "type": event_type,
            "timestamp": time.time(),
            "details": details
        }
        if self._staging is not None:
            self._staging.setdefault("telemetry_stream", []).append(entry)
        else:
            self._telemetry_stream.append(entry)
        # Heatmap update for regional activity
        if "region_id" in details:
            self.pulse_heatmap(details["region_id"], 1.0)
            
        self._record("emit_telemetry", {"type": event_type})

    def pulse_heatmap(self, region_id: str, intensity: float):
        """Increase activity score for a specific region."""
        heatmap = self._get_struct("activity_heatmap")
        current = heatmap.get(region_id, 0.0)
        heatmap[region_id] = min(10.0, current + intensity)
        self._set_struct("activity_heatmap", heatmap)

    def log_drift(self, role: str, drift: float):
        """Record manifold drift for a role."""
        log = self._get_struct("drift_log")
        if role not in log:
            log[role] = deque(maxlen=100)
        log[role].append(drift)
        self._set_struct("drift_log", log)

    def decay_heatmap(self, rate: float = 0.9):
        """Gradually decay heatmap scores to reflect cooling activity."""
        heatmap = self._get_struct("activity_heatmap")
        for rid in list(heatmap.keys()):
            heatmap[rid] *= rate
            if heatmap[rid] < 0.01:
                del heatmap[rid]
        self._set_struct("activity_heatmap", heatmap)

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def telemetry(self) -> List[dict]:
        return list(self._telemetry_stream)

    @property
    def heatmap(self) -> Dict[str, float]:
        return dict(self._get_struct("activity_heatmap"))

    def get_role_drift(self, role: str) -> List[float]:
        log = self._get_struct("drift_log")
        return list(log.get(role, []))

    def get_causal_telemetry(self) -> List[dict]:
        """Return formatted transaction lineages for visualization."""
        journal = self._telemetry_stream # Using telemetry stream for now
        # Filtering for transaction-related events
        return [t for t in journal if t["type"] in ["transaction", "merge_branch", "federation"]]

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "observability": {
                "activity_heatmap": self.heatmap,
                "drift_log": {k: list(v) for k, v in self._get_struct("drift_log").items()},
                "telemetry_stream": list(self._telemetry_stream),
            }
        }

    def from_dict(self, data: dict):
        self.clear()
        obs_data = data.get("observability", {})
        self._set_struct("activity_heatmap", dict(obs_data.get("activity_heatmap", {})))
        raw_drift = obs_data.get("drift_log", {})
        self._set_struct("drift_log", {k: deque(v, maxlen=100) for k, v in raw_drift.items()})
        raw_telemetry = obs_data.get("telemetry_stream", [])
        if self._staging is not None:
            self._staging["telemetry_stream"] = list(raw_telemetry)
        else:
            self._telemetry_stream = deque(raw_telemetry, maxlen=1000)

    def clear(self):
        if self._staging is not None:
            self._staging["telemetry_stream"] = []
        else:
            self._telemetry_stream.clear()
        self._set_struct("activity_heatmap", {})
        self._set_struct("drift_log", {})

# ─── Legacy Observability Utilities ──────────────────────────────────

def field_summary(ws) -> dict:
    """Return a summary of the field's current energetic state."""
    return {
        "energy": ws.metrics.global_energy,
        "entropy": ws.metrics.global_entropy,
        "temperature": ws.metrics.semantic_temperature,
        "integrity": ws.metrics.integrity_score
    }

def topology_report(ws) -> dict:
    """Return a detailed report of the manifold's topology."""
    return {
        "pressure": ws.get_system_pressure(),
        "region_count": ws.get_topology_view().region_count(),
        "role_count": len(ws.role_manifold),
        "community_count": len(ws.global_communities)
    }
