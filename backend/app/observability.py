"""Cognitive Observability — owns field-native telemetry and heatmap data.

True ownership boundary: NO external code should mutate telemetry_stream directly.
All changes go through this state object, which supports transactions.
"""

import logging
import time
from typing import Dict, List, Optional, Callable, Any
from app.transaction_context import active_transaction

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

    @property
    def _staging(self) -> Optional[dict]:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"observability_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: Optional[dict]):
        tx = active_transaction.get()
        if tx is not None:
            tx[f"observability_staging_{id(self)}"] = value

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

    def emit_telemetry(self, event_type: str, details: dict, trace_id: Optional[str] = None):
        """Record a cognitive event in the telemetry stream (Phase 41)."""
        entry = {
            "type": event_type,
            "timestamp": time.time(),
            "details": details,
        }
        if trace_id:
            entry["trace_id"] = trace_id
        if self._staging is not None:
            self._staging.setdefault("telemetry_stream", []).append(entry)
        else:
            self._telemetry_stream.append(entry)
        # Heatmap update for regional activity
        if "region_id" in details:
            self.pulse_heatmap(details["region_id"], 1.0)
            
        self._record("emit_telemetry", {"type": event_type, "details": details, "trace_id": trace_id})

    def record_degradation(self, subsystem: str, severity: str, cause: str,
                             trace_id: Optional[str] = None,
                             topology_state: Optional[str] = None,
                             semantic_entropy: Optional[float] = None):
        """Record a structured degradation event with causality tracking.

        This ensures silent fallback paths are visible in telemetry,
        enabling causal explainability for semantic drift, topology
        destabilization, and inference quality degradation.
        """
        details: Dict[str, Any] = {
            "subsystem": subsystem,
            "severity": severity,
            "cause": cause,
        }
        if topology_state is not None:
            details["topology_state"] = topology_state
        if semantic_entropy is not None:
            details["semantic_entropy"] = semantic_entropy

        self.emit_telemetry("degradation", details, trace_id=trace_id)

        # Log to standard logging as well
        log_msg = f"DEGRADATION [{severity.upper()}] {subsystem}: {cause}"
        if trace_id:
            tid_str = str(trace_id)
            log_msg += f" (trace: {tid_str})"
        if severity == "critical":
            logging.getLogger(__name__).critical(log_msg)
        elif severity == "warning":
            logging.getLogger(__name__).warning(log_msg)
        else:
            logging.getLogger(__name__).info(log_msg)

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
        self._record("decay_heatmap", {"rate": rate})

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

    def detect_oscillations(self, snapshots: List[dict], window: int = 20) -> List[dict]:
        """Analyze state history for cyclic instability or energy patterns (Phase 46)."""
        if len(snapshots) < window:
            return []
            
        oscillations = []
        energies = [s.get("energy", 0.0) for s in snapshots[-window:]]
        if self._is_cyclic(energies):
            oscillations.append({
                "type": "global_energy",
                "confidence": 0.8,
                "period": self._estimate_period(energies)
            })
            
        return oscillations

    def calculate_attractor_diversity(self, ws) -> float:
        """Quantify the semantic field plasticity using Shannon entropy (Phase 56).
        
        High Diversity = Many active basins with varied stability.
        Low Diversity = Dominant basins suppressing exploration (Freezing).
        """
        manifold = ws.role_manifold
        if not manifold:
            return 1.0
            
        stabilities = [ws._manifold.get_role_certainty(r) for r in manifold]
        if not stabilities:
            return 1.0
            
        # Normalize to probability-like distribution
        total = sum(stabilities)
        if total == 0:
            return 0.0
            
        probs = [s / total for s in stabilities]
        
        import math
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        
        # Scale by log of number of roles to get [0, 1] range
        max_entropy = math.log2(len(manifold)) if len(manifold) > 1 else 1.0
        return entropy / max_entropy

    def get_governance_report(self, ws) -> dict:
        """Summary of emergent systems health and governance status (Phase 56)."""
        snapshots = ws._history.topology_snapshots
        manifold_history = {r: self.get_role_drift(r) for r in ws.role_manifold}
        
        report = {
            "diversity": round(self.calculate_attractor_diversity(ws), 3),
            "oscillations": self.detect_oscillations(snapshots),
            "runaways": self.detect_runaway_attractors(manifold_history),
            "memory_usage": self.get_memory_profile(ws),
            "is_locked": self.detect_metastable_locks(
                [s.get("energy", 0.0) for s in snapshots],
                [s.get("entropy", 0.0) for s in snapshots]
            )
        }
        return report

    def calculate_damping_factor(self, snapshots: List[dict]) -> float:
        """Compute a global damping factor based on detected instability patterns (Phase 49).
        
        Factor 1.0 = No damping.
        Factor < 1.0 = Suppress propagation gain to prevent divergence.
        """
        oscillations = self.detect_oscillations(snapshots)
        if not oscillations:
            return 1.0
            
        # Maximum damping for strong oscillations
        max_conf = max(o["confidence"] for o in oscillations)
        return max(0.2, 1.0 - max_conf * 0.8)

    def get_stability_policy(self, ws) -> dict:
        """Return a dynamic stabilization policy for the current field state (Phase 49)."""
        snapshots = ws._history.topology_snapshots
        damping = self.calculate_damping_factor(snapshots)
        
        # Check for runaways
        manifold_history = {r: self.get_role_drift(r) for r in ws.role_manifold}
        runaways = self.detect_runaway_attractors(manifold_history)
        
        policy = {
            "propagation_damping": damping,
            "force_decay": ws.metrics.global_energy > 8.0,
            "attractor_scaling": 0.5 if runaways else 1.0,
            "lock_escape_required": self.detect_metastable_locks(
                [s.get("energy", 0.0) for s in snapshots],
                [s.get("entropy", 0.0) for s in snapshots]
            )
        }
        return policy

    def detect_runaway_attractors(self, manifold_history: Dict[str, List[float]], threshold: float = 0.95) -> List[dict]:
        """Identify roles that have become 'too stable' or dominant (Phase 48).
        
        Runaway attractors can freeze the field and prevent new learning.
        """
        runaways = []
        for role, history in manifold_history.items():
            if len(history) < 20:
                continue
            recent = history[-20:]
            # If variance is near-zero and position is at an extreme
            avg_pos = sum(recent) / len(recent)
            variance = sum((x - avg_pos)**2 for x in recent) / len(recent)
            if variance < 1e-6 and abs(avg_pos) > threshold:
                runaways.append({"role": role, "stability": avg_pos, "risk": "field_freezing"})
        return runaways

    def detect_metastable_locks(self, energy_history: List[float], entropy_history: List[float]) -> bool:
        """Identify if the system is stuck in a local minimum (Phase 48)."""
        if len(energy_history) < 50:
            return False
        
        recent_e = energy_history[-50:]
        recent_s = entropy_history[-50:]
        
        e_stable = (max(recent_e) - min(recent_e)) < 0.02
        s_stable = (max(recent_s) - min(recent_s)) < 0.02
        
        # High stable energy + low stable entropy = likely stuck
        # (Threshold 8.0 prevents baseline thrashing at default 5.0)
        return e_stable and s_stable and recent_e[0] > 8.0 and recent_s[0] < 0.2

    def compress_causal_history(self, threshold_age_sec: float = 3600):
        """Compress old telemetry events into causal summaries (Phase 48).
        
        Prevents causal graph explosion while maintaining long-term traceability.
        """
        now = time.time()
        stream = list(self._telemetry_stream)
        if not stream:
            return
            
        to_keep = []
        to_compress = []
        
        for entry in stream:
            if now - entry["timestamp"] < threshold_age_sec:
                to_keep.append(entry)
            else:
                to_compress.append(entry)
                
        if not to_compress:
            return
            
        # Summarize compressed events by type
        summary = {
            "type": "causal_summary",
            "timestamp": to_compress[-1]["timestamp"],
            "details": {
                "period_start": to_compress[0]["timestamp"],
                "period_end": to_compress[-1]["timestamp"],
                "event_counts": {},
                "compressed_count": len(to_compress),
                "energy_stats": {},
                "entropy_stats": {}
            }
        }
        energies = []
        entropies = []
        for entry in to_compress:
            etype = entry["type"]
            summary["details"]["event_counts"][etype] = summary["details"]["event_counts"].get(etype, 0) + 1
            if "energy" in entry.get("details", {}):
                energies.append(entry["details"]["energy"])
            if "entropy" in entry.get("details", {}):
                entropies.append(entry["details"]["entropy"])
                
        if energies:
            summary["details"]["energy_stats"] = {
                "min": min(energies), "max": max(energies), "avg": sum(energies)/len(energies)
            }
        if entropies:
            summary["details"]["entropy_stats"] = {
                "min": min(entropies), "max": max(entropies), "avg": sum(entropies)/len(entropies)
            }
            
        new_stream = [summary] + to_keep
        if self._staging is not None:
            self._staging["telemetry_stream"] = new_stream
        else:
            self._telemetry_stream = deque(new_stream, maxlen=1000)
        
        self._record("compress_history", {"compressed": len(to_compress)})

    def _is_cyclic(self, values: List[float]) -> bool:
        """Simple autocorrelation-based cycle detection."""
        if not values or len(values) < 8:
            return False
        # Mean-center
        avg = sum(values) / len(values)
        centered = [v - avg for v in values]
        
        # Check for sign-flip frequency
        flips = 0
        for i in range(1, len(centered)):
            if (centered[i-1] > 0 and centered[i] < 0) or \
               (centered[i-1] < 0 and centered[i] > 0):
                flips += 1
        
        # High number of flips relative to window size indicates oscillation
        n = len(values)
        return flips >= (n // 4) if n > 0 else False

    def _estimate_period(self, values: List[float]) -> int:
        """Estimate the period of a detected oscillation."""
        # Implementation: count distance between peaks
        peaks = []
        for i in range(1, len(values) - 1):
            if values[i] > values[i-1] and values[i] > values[i+1]:
                peaks.append(i)
        if len(peaks) < 2:
            return 0
        return (peaks[-1] - peaks[0]) // (len(peaks) - 1)

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

    def get_memory_profile(self, ws) -> dict:
        """Measure the size of the semantic world state subsystems (Phase 47)."""
        import sys
        
        def get_size(obj):
            if hasattr(obj, 'to_dict'):
                # Approximating size via serialized dictionary
                import json
                return len(json.dumps(obj.to_dict()))
            return sys.getsizeof(obj)
            
        profile = {
            "topology": get_size(ws._topology),
            "manifold": get_size(ws._manifold),
            "motif": get_size(ws._motif),
            "history": get_size(ws._history),
            "telemetry": get_size(self._telemetry_stream),
            "total_records": ws.metrics.total_records_processed
        }
        profile["total_estimated_bytes"] = sum(v for k, v in profile.items() if k != "total_records")
        return profile

    def calculate_semantic_importance(self, region, ws) -> float:
        """Compute the topological importance of a region (Phase 50).
        
        High Importance = high centrality, low instability, and participation in stable motifs.
        """
        # 1. Centrality (if available in topology state)
        centrality = ws._topology._centrality.get(region.region_id, 0.5)
        
        # 2. Stability boost
        stability = 1.0 - region.instability
        
        # 3. Persistence factor
        persistence = region.persistence
        
        return (centrality * 0.4) + (stability * 0.3) + (persistence * 0.3)

    def apply_resource_shedding(self, ws, max_bytes: int = 10000000):
        """Prune non-essential state if memory footprint exceeds threshold (Phase 47/50).
        
        Enhanced with Value-Aware Pruning to preserve semantic continuity.
        """
        profile = self.get_memory_profile(ws)
        if profile["total_estimated_bytes"] < max_bytes:
            return False
            
        logging.warning("RESOURCE SHEDDING TRIGGERED: Substrate memory [%d] exceeds threshold [%d]", 
                        profile["total_estimated_bytes"], max_bytes)
        
        # 1. Prune Telemetry (tail-heavy)
        old_telemetry = len(self._telemetry_stream)
        self._telemetry_stream = deque(list(self._telemetry_stream)[-100:], maxlen=1000)
        
        # 2. Prune History
        ws._history.trim_journal(200)
        ws._history.trim_snapshots(50)
        
        # 3. Value-Aware Region Pruning (Phase 50)
        # Instead of just trimming from end, we sort by importance
        regs = ws._topology._get_regions()
        if len(regs) > 50:
            # Rank by importance
            scored_regs = [(self.calculate_semantic_importance(r, ws), r) for r in regs]
            scored_regs.sort(key=lambda x: x[0], reverse=True) # highest importance first
            
            # Keep top 50
            kept_regs = [r for score, r in scored_regs[:50]]
            ws._topology.replace_all(kept_regs)
        
        # 4. Prune Weak Motifs
        ws._motif.prune_weak(threshold=0.2)
        
        self.emit_telemetry("resource_shedding", {
            "old_bytes": profile["total_estimated_bytes"],
            "telemetry_pruned": old_telemetry - len(self._telemetry_stream),
            "regions_count": len(ws._topology._get_regions())
        })
        return True
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
