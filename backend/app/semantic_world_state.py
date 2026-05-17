import logging
import time
from collections import Counter
from typing import Dict, List, Tuple, Optional, Any, Set, Callable
from contextlib import contextmanager

from app.core_types import FieldConflictRegion
from app.invariant_firewall import requires_invariants

class SemanticWorldState:
    """
    Canonical Semantic World State — now a true orchestrator.
    
    Meaning emerges from the relational topology of this state.
    No subsystem may maintain isolated semantic truth.
    """
    def __init__(self, node_id: Optional[str] = None):
        from app.topology_state import TopologyState
        from app.energy_state import EnergyState
        from app.instability_state import InstabilityState
        from app.manifold_state import ManifoldState
        from app.motif_state import MotifState
        from app.transition_state import TransitionState
        from app.history_state import HistoryState
        from app.vector_clock import VectorClock
        from app.intent_state import IntentState
        from app.action_state import ActionState
        from app.abstraction_state import AbstractionState
        from app.graph_update_scheduler import GlobalCognitiveScheduler
        from app.observability import ObservabilityState
        import uuid
        
        self._node_id = node_id or str(uuid.uuid4())[:8]
        self._vector_clock = VectorClock(self._node_id)
        
        self._topology = TopologyState(delta_callback=self.record_delta)
        self._energy = EnergyState(delta_callback=self.record_delta)
        self._instability = InstabilityState(delta_callback=self.record_delta)
        self._manifold = ManifoldState(delta_callback=self.record_delta)
        self._motif = MotifState(delta_callback=self.record_delta)
        self._transition = TransitionState(delta_callback=self.record_delta)
        self._intent = IntentState(delta_callback=self.record_delta)
        self._action = ActionState(delta_callback=self.record_delta)
        self._abstraction = AbstractionState(delta_callback=self.record_delta)
        self._observability = ObservabilityState(delta_callback=self.record_delta)
        self._history = HistoryState()
        self._scheduler = GlobalCognitiveScheduler(ws=self)
        
        self.metrics = self._energy
        self.last_update_time: float = time.time()
        self._transaction_depth = 0
        self._replaying = False
        self._active_trace_id: Optional[str] = None
        self._current_journal: List[dict] = []
        self._global_journal: List[dict] = []
        self._evolved_schema: Set[str] = set()
        
        # Substrate Branching (Phase 39)
        self._parent_node_id: Optional[str] = None
        self._branch_label: Optional[str] = None

    def branch(self, label: str) -> "SemanticWorldState":
        """Create an isolated branch of the current semantic world (Phase 39)."""
        import uuid
        child_id = f"{self._node_id}-br-{str(uuid.uuid4())[:4]}"
        child = SemanticWorldState(node_id=child_id)
        
        # Clone state via serialization
        state_snapshot = self.to_dict()
        child.from_dict(state_snapshot)
        
        # RESTORE the unique child ID and parent lineage
        child.node_id = child_id
        child._parent_node_id = self._node_id
        child._branch_label = label
        
        # Initialize child's vector clock as a descendant of parent
        child._vector_clock.update(self._vector_clock.get_clock())
        
        logging.getLogger(__name__).info(
            f"SUBSTRATE BRANCHED: [{self.node_id}] -> [{child_id}] (Label: {label})"
        )
        return child

    @contextmanager
    def transaction(self, label: str = "anonymous", trace_id: Optional[str] = None):
        """Context manager for atomic state transactions. Supports nesting and causality tracing."""
        states = [self._topology, self._energy, self._instability, 
                  self._manifold, self._motif, self._transition, 
                  self._intent, self._action, self._abstraction, self._observability]
        
        import uuid
        if self._transaction_depth == 0:
            for s in states:
                if hasattr(s, 'begin_transaction'):
                    s.begin_transaction()
            self._current_journal = []
            # Start new trace or use provided one
            self._active_trace_id = trace_id or str(uuid.uuid4())[:8]
        
        self._transaction_depth += 1
        start_time = time.time()
        try:
            yield self
            if self._transaction_depth == 1:
                # Increment vector clock on commit (Phase 32)
                self._vector_clock.increment()
                
                for s in states:
                    if hasattr(s, 'commit'):
                        s.commit()
                self.last_update_time = time.time()
                # Record transaction in global journal
                tx = {
                    "label": label,
                    "timestamp": self.last_update_time,
                    "duration": self.last_update_time - start_time,
                    "clock": self._vector_clock.get_clock(),
                    "node_id": self.node_id,
                    "trace_id": self._active_trace_id,
                    "entries": list(self._current_journal)
                }
                self._global_journal.append(tx)
                self._history.record_transaction(tx)
                # Trim global journal
                if len(self._global_journal) > 1000:
                    self._global_journal = self._global_journal[-500:]
        except Exception as e:
            if self._transaction_depth == 1:
                for s in states:
                    if hasattr(s, 'rollback'):
                        s.rollback()
                logging.getLogger(__name__).error(f"State transaction [{label}] failed on node [{self.node_id}] (Trace: {self._active_trace_id}), rolled back: {e}")
            raise
        finally:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                self._active_trace_id = None

    def replay_transaction(self, tx: dict):
        """Replay a transaction by executing its recorded entries.
        
        This enables deterministic replay of field dynamics.
        """
        label = tx.get("label", "replayed")
        self._replaying = True
        try:
            with self.transaction(f"replay:{label}"):
                for entry in tx.get("entries", []):
                    subsystem = entry.get("subsystem")
                    action = entry.get("action")
                    details = entry.get("details", {})
                    
                    # Automated Exhaustive Dispatching (Phase 28)
                    target: Any = None
                    if subsystem == "topology": target = self._topology
                    elif subsystem == "energy": target = self._energy
                    elif subsystem == "instability": target = self._instability
                    elif subsystem == "manifold": target = self._manifold
                    elif subsystem == "motif": target = self._motif
                    elif subsystem == "transition": target = self._transition
                    elif subsystem == "intent": target = self._intent
                    elif subsystem == "action": target = self._action
                    elif subsystem == "abstraction": target = self._abstraction
                    elif subsystem == "observability": target = self._observability
                    
                    if target and hasattr(target, action):
                        method = getattr(target, action)
                        try:
                            # Fix for json-serialized tuple keys
                            if subsystem == "instability" and "key" in details:
                                details["key"] = tuple(details["key"])
                            if subsystem == "manifold" and "key" in details:
                                details["key"] = tuple(details["key"])
                                
                            method(**details)
                        except Exception as e:
                            logging.getLogger(__name__).warning(
                                f"Replay failed for {subsystem}.{action}: {e}"
                            )
                    
                    logging.getLogger(__name__).debug(f"Replayed: {subsystem}.{action}({details})")
        finally:
            self._replaying = False

    def record_delta(self, subsystem: str, action: str, details: dict):
        """Record a state delta in the current transaction journal."""
        if self._replaying:
            return
            
        entry = {
            "subsystem": subsystem,
            "action": action,
            "details": details,
            "timestamp": time.time(),
            "trace_id": self._active_trace_id
        }
        if self._transaction_depth > 0:
            self._current_journal.append(entry)
        else:
            # Direct mutation outside transaction (less ideal but possible)
            self._global_journal.append({
                "label": "direct_mutation",
                "timestamp": entry["timestamp"],
                "duration": 0,
                "entries": [entry]
            })

    def trace_causality(self, limit: int = 100) -> List[dict]:
        """Return the causality journal."""
        return self._global_journal[-limit:]

    # ─── Distributed Consensus (Phase 32) ───────────────────────────────

    def merge_state(self, remote_data: dict, trace_id: Optional[str] = None):
        """Merge a remote world state into the local state using vector clocks (Phase 32)."""
        remote_node = remote_data.get("node_id")
        remote_clock = remote_data.get("clock", {})
        
        # Use provided trace_id or fallback to remote's last_trace_id
        active_trace = trace_id or remote_data.get("last_trace_id")
        
        # 1. Compare Clocks to determine causality
        relation = self._vector_clock.compare(remote_clock)
        
        if relation == "ancestor" or relation == "equal":
            # Remote is behind or identical; ignore
            logging.getLogger(__name__).info(f"CONSENSUS: Ignoring remote state from [{remote_node}] (Ancestor/Equal)")
            return
            
        with self.transaction(f"merge:{remote_node}", trace_id=active_trace):
            # Update local clock with remote knowledge
            self._vector_clock.update(remote_clock)
            
            # Semantic Reconciliation: determine blending factor (alpha)
            # If concurrent (conflict), use conservative blending (0.3)
            # If descendant (remote is newer), use aggressive blending (0.7)
            alpha = 0.7 if relation == "descendant" else 0.3
            
            # 2. Merge Sub-States
            self._energy.merge(remote_data, alpha=alpha)
            self._manifold.merge(remote_data, alpha=alpha)
            self._instability.merge(remote_data)
            self._topology.merge(remote_data.get("topology", {}), alpha=alpha)
            
            # Merge evolved schema
            remote_schema = set(remote_data.get("evolved_schema", []))
            self._evolved_schema.update(remote_schema)
            
            logging.getLogger(__name__).info(
                f"CONSENSUS: Merged state from [{remote_node}]. Relation: {relation}, Alpha: {alpha} (Trace: {active_trace})"
            )
            self.record_delta("global", "merge_state", {
                "remote_node": remote_node,
                "relation": relation,
                "alpha": alpha,
                "remote_trace": remote_data.get("last_trace_id")
            })

    # ─── Manifold Federation ─────────────────────────────────────────────

    def export_manifold(self) -> dict:
        """Export learned role embeddings with Differential Noise (Phase 30)."""
        import random
        manifold = self.role_manifold
        
        # Apply Differential Noise to protect local training data privacy
        for role in manifold:
            vec = manifold[role]
            # Noise epsilon = 0.01 (small enough to preserve meaning, large enough for epsilon-privacy)
            noise = [random.gauss(0, 0.01) for _ in range(16)]
            for i in range(16):
                vec[i] = max(0.0, min(1.0, vec[i] + noise[i]))
            manifold[role] = vec

        return {
            "manifold": manifold,
            "version": "1.1",
            "timestamp": time.time(),
            "origin": id(self),
            "privacy": "differential_noise_v1"
        }

    def import_federated_manifold(self, data: dict):
        """Merge federated role embeddings into local manifold with Ontological Firewall (Phase 30)."""
        remote_manifold = data.get("manifold", {})
        with self.transaction("manifold_federation"):
            filtered_count = 0
            for role, remote_vec in remote_manifold.items():
                # ─── Ontological Firewall ───
                # 1. Entropy Filter: ignore undifferentiated vectors (mostly 0.5)
                # Max entropy = 0.5 across all 16 dimensions
                entropy = sum(1.0 - abs(v - 0.5) * 2.0 for v in remote_vec) / 16.0
                if entropy > 0.9: # Too much uncertainty in remote data
                    filtered_count += 1
                    continue
                
                if self._manifold.has_manifold_role(role):
                    # 2. Contradiction Filter: if local is anchored or very stable,
                    # and remote is extremely far away, ignore it.
                    if self._manifold.is_role_anchored(role):
                        filtered_count += 1
                        continue
                    
                    local_vec = self._manifold.get_manifold_vector(role)
                    # Euclidean distance
                    dist = sum((a - b)**2 for a, b in zip(local_vec, remote_vec))**0.5
                    if dist > 1.5: # Extremely contradictory
                        filtered_count += 1
                        continue

                    # Thermodynamic Merger
                    self._manifold.blend_manifold_vector(role, remote_vec, alpha=0.8, beta=0.2)
                else:
                    # Knowledge Acquisition
                    self._manifold.set_manifold_vector(role, remote_vec)
                    self._energy.set_schema_instability(role, 0.3)
            
            logging.getLogger(__name__).info(
                f"FEDERATION: Merged {len(remote_manifold) - filtered_count} roles. "
                f"Firewall filtered {filtered_count} high-entropy/contradictory roles."
            )
            self.record_delta("global", "manifold_federation", {
                "remote_roles": len(remote_manifold),
                "filtered": filtered_count
            })

    def export_topology_laws(self) -> dict:
        """Export learned topological laws for federation."""
        return {
            "laws": {f"{k[0]}|{k[1]}": v for k, v in self._topology.topological_laws.items()},
            "version": "1.0",
            "timestamp": time.time()
        }

    def import_federated_laws(self, data: dict):
        """Merge federated topological laws into local state (Phase 29)."""
        remote_laws = data.get("laws", {})
        with self.transaction("federated_laws"):
            for key_str, remote_val in remote_laws.items():
                parts = key_str.split("|")
                if len(parts) == 2:
                    pair = tuple(parts)
                    local_val = self._topology.topological_laws.get(pair, 0.0)
                    # Consensus Algorithm: Conservative Blending
                    # Local(0.7) + Remote(0.3)
                    new_val = local_val * 0.7 + remote_val * 0.3
                    self._topology.set_topological_law(pair, new_val)
            
            logging.getLogger(__name__).info(f"FEDERATION: Merged {len(remote_laws)} topological laws.")
            self.record_delta("global", "federated_laws", {"remote_laws": len(remote_laws)})

    def get_cognitive_health(self) -> dict:
        """Provide a summary of the engine's cognitive health (Phase 30)."""
        from app.semantic_inference_engine import RoleEmbeddingEngine
        reng = RoleEmbeddingEngine()
        
        certainty = reng.get_certainty()
        roles = self._manifold.get_manifold_roles()
        active_roles = [r for r in roles if not r.startswith("hypo_")]
        hypo_roles = [r for r in roles if r.startswith("hypo_")]
        
        # Fragmentation: how many disjoint communities exist relative to role count
        communities = self.global_communities
        fragmentation = len(communities) / max(len(active_roles), 1)
        
        # Alignment: how close roles are to their seed types on average
        from app.semantic_allocation_engine import _infer_role_type
        alignment_total = 0.0
        for role in active_roles:
            seed_type = _infer_role_type(role)
            seed_vec = reng._get_type_vector(seed_type)
            role_vec = self._manifold.get_manifold_vector(role)
            # Cosine similarity-like dot product
            alignment = sum(a * b for a, b in zip(seed_vec, role_vec)) / 16.0
            alignment_total += alignment
        
        avg_alignment = alignment_total / max(len(active_roles), 1)
        
        return {
            "overall_health": round(avg_alignment * (1.0 - fragmentation * 0.5), 3),
            "certainty": round(certainty, 3),
            "alignment": round(avg_alignment, 3),
            "fragmentation": round(fragmentation, 3),
            "role_stats": {
                "total": len(roles),
                "active": len(active_roles),
                "hypo": len(hypo_roles),
                "anchored": len(self._manifold.role_anchors)
            },
            "system_energy": round(self.metrics.global_energy, 3),
            "stability_debt": round(self.metrics.stability_debt, 3)
        }

    # ─── Authority Delegation Properties ─────────────────────────────────
    # These delegate to state objects. Direct self.field_regions / self.learned_exclusions
    # references in this class work transparently through these properties.
    # The state objects are the TRUE owners.

    @property
    def field_regions(self):
        """Return immutable RegionSnapshot objects.

        For mutation, use the controlled TopologyState API through
        self._topology methods (find_region_for_mutation, set_region_instability, etc.).
        """
        return self._topology.get_view().all_regions()

    @field_regions.setter
    def field_regions(self, value):
        self._topology.replace_all(list(value))

    @property
    def learned_exclusions(self):
        # Return a copy to prevent reference aliasing from external code
        return dict(self._instability.exclusions)

    # ─── Delegation Properties: ManifoldState ─────────────────────────────

    @property
    def role_manifold(self):
        # Deep copy to prevent reference aliasing from external code
        return {k: list(v) for k, v in self._manifold.role_manifold.items()}

    @property
    def role_compatibility(self):
        # Return a copy to prevent reference aliasing from external code
        return dict(self._manifold.role_compatibility)

    @property
    def role_position_memory(self):
        # Deep copy to prevent reference aliasing from external code
        return {k: list(v) for k, v in self._manifold.role_position_memory.items()}

    @role_position_memory.setter
    def role_position_memory(self, value):
        self._manifold.role_position_memory = value

    @property
    def role_co_occurrence(self):
        # Return a copy to prevent reference aliasing from external code
        return dict(self._manifold.role_co_occurrence)

    @property
    def learning_count(self):
        return self._manifold.learning_count

    @learning_count.setter
    def learning_count(self, value):
        self._manifold.set_learning_count(value)

    @property
    def total_co_occurrences(self):
        return self._manifold.total_co_occurrences

    @total_co_occurrences.setter
    def total_co_occurrences(self, value):
        self._manifold.set_total_co_occurrences(value)

    # ─── Delegation Properties: MotifState ───────────────────────────────

    @property
    def motif_counts(self):
        return Counter(self._motif.motif_counts)

    @property
    def motif_timestamps(self):
        return dict(self._motif.motif_timestamps)

    @property
    def motif_stability(self):
        return dict(self._motif.motif_stability)

    # ─── Delegation Properties: TransitionState ───────────────────────────

    @property
    def transition_probs(self):
        return dict(self._transition.transition_probs)

    @property
    def transition_observations(self):
        return self._transition.transition_observations

    @transition_observations.setter
    def transition_observations(self, value):
        self._transition.set_transition_observations(value)

    # ─── Delegation Properties: HistoryState ──────────────────────────────

    @property
    def decision_history(self):
        return list(self._history.decision_history)

    @decision_history.setter
    def decision_history(self, value):
        self._history.decision_history = value

    @property
    def topology_snapshots(self):
        return list(self._history.topology_snapshots)

    @topology_snapshots.setter
    def topology_snapshots(self, value):
        self._history.topology_snapshots = value

    @property
    def crystalline_records(self):
        return list(self._history.crystalline_records)

    @property
    def field_activation_count(self):
        return self._history.field_activation_count

    @field_activation_count.setter
    def field_activation_count(self, value):
        self._history.field_activation_count = value

    @property
    def dataset_consensus(self):
        return dict(self._history.dataset_consensus)

    @property
    def solidified_motifs(self):
        return list(self._history.solidified_motifs)

    # ─── Delegation Properties: Topology-Derived Structures ───────────────

    @property
    def global_communities(self):
        return [set(c) for c in self._topology.global_communities]

    @property
    def schema_patterns(self):
        return dict(self._topology.schema_patterns)

    @property
    def topological_laws(self):
        return dict(self._topology.topological_laws)

    @property
    def neighborhood_cohesion(self):
        return dict(self._topology.neighborhood_cohesion)

    @property
    def global_centrality(self):
        return dict(self._topology.global_centrality)

    @property
    def impossible_neighborhoods(self):
        return [set(c) for c in self._topology.impossible_neighborhoods]

    @property
    def restructuring_queue(self):
        return set(self._topology.restructuring_queue)

    @property
    def cohesion_merge_success(self):
        return dict(self._topology.get_cohesion_merge_success())

    @property
    def cohesion_merge_attempts(self):
        return dict(self._topology.get_cohesion_merge_attempts())

    @property
    def cohesion_split_success(self):
        return dict(self._topology.get_cohesion_split_success())

    @property
    def cohesion_split_attempts(self):
        return dict(self._topology.get_cohesion_split_attempts())

    @requires_invariants
    def reinforce_motif(self, motif: Tuple[str, ...]):
        """Reinforce a structural motif with temporal awareness."""
        self._motif.reinforce(motif, self.metrics.total_records_processed)

    def get_motif_stability(self, motif: Tuple[str, ...]) -> float:
        """Get temporal stability score for a motif (0-1)."""
        return self._motif.compute_stability(motif, self.metrics.total_records_processed)

    @requires_invariants
    def apply_memory_decay(self):
        """Globally decay old or weak semantic structures to reduce entropy.
        
        LAW 5: No fixed evolution cadence. Decay is triggered by field demand
        (entropy disorder or field pressure), not a procedural record counter.
        """
        # Field-demand trigger: decay when entropy is high (needs cleanup)
        # or when pressure is moderate (some tension to resolve).
        # Minimum context guard prevents firing on initialization defaults
        # (global_entropy starts at 0.5, above the 0.4 threshold).
        has_context = self.metrics.total_records_processed >= 5
        should_decay = has_context and (self.metrics.global_entropy > 0.4 or
                                        self.metrics.field_pressure > 0.3)
        if not should_decay:
            return
        self._manifold.decay_compatibilities(rate=0.01)
        self._motif.prune_aged(max_stability=0.01)

    def get_derived_exclusion(self, role_a: str, role_b: str) -> float:
        """Compute exclusion strength from topology metrics — the dict is secondary.

        Exclusion emerges from topology itself:
        1. Motif instability: if motifs containing these roles are unstable, exclude more
        2. Compatibility divergence: roles with divergent type preferences exclude more
        3. Neighborhood instability: if roles are in different neighborhoods, exclude more
        4. Learned exclusion history (symbolic bridge, secondary)

        The topology baseline produces non-zero exclusion even when the dict is empty.
        The dict only amplifies patterns already visible in the topology.
        """
        baseline = 0.0

        # 1. Motif pressure (topology-native): unstable motifs → exclusion
        # Stable motifs REPEL exclusion (they indicate compatible neighborhoods)
        ra_types = {t for r, t in self.role_compatibility if r == role_a}
        rb_types = {t for r, t in self.role_compatibility if r == role_b}
        for motif in self.motif_counts:
            if any(t in motif for t in ra_types) and any(t in motif for t in rb_types):
                stability = self.get_motif_stability(motif)
                if stability < 0.5:
                    baseline += 0.18 * (0.5 - stability)
                else:
                    baseline -= 0.03 * (stability - 0.5)

        # 2. Compatibility pressure (topology-native): divergent type preferences → exclusion
        observed_types = set()
        for r, t in self.role_compatibility:
            observed_types.add(t)
        for ttype in observed_types:
            ca = self.role_compatibility.get((role_a, ttype), 0.5)
            cb = self.role_compatibility.get((role_b, ttype), 0.5)
            if abs(ca - cb) > 0.2:
                baseline += 0.06

        # 3. Topology persistence: stable field regions reduce exclusion
        view = self._topology.get_view()
        for region in view.all_regions():
            if role_a in region.competing_roles and role_b in region.competing_roles:
                if region.instability < 0.3:
                    baseline -= 0.05

        # 4. Learned exclusion (symbolic bridge, secondary cache — 0.1x weight)
        key = tuple(sorted([role_a, role_b]))
        learned = self.learned_exclusions.get(key, 0.0) * 0.1
        total = baseline + learned

        return max(0.0, min(1.0, total))

    @property
    def topology_density(self) -> float:
        """Graph interconnectedness — edges per possible role pair.

        Dense topology = many exclusivity relationships = conflicts
        propagate easily. Used to tighten exclusion thresholds so the
        graph geometry itself governs cognition.
        """
        from app.field_laws import ROLE_EXCLUSIVITY
        possible = len(ROLE_EXCLUSIVITY) + max(len(self.learned_exclusions), 1)
        actual = len(self.learned_exclusions)
        return min(actual / possible, 1.0) if possible > 0 else 0.0

    @requires_invariants
    def propagate_field_regions(self) -> int:
        """Each basin owns its own propagation — deltas applied through formal APIs."""
        with self.transaction("propagation"):
            from app.failure_injector import get_injector
            get_injector().inject("propagate_field_regions")
            
            # Use TopologyState's bulk propagation instead of manual iteration
            self._topology.propagate_all(ws=self)
            count = self._topology.region_count()
            self.record_delta("topology", "propagate_all", {"regions": count})
            return count

    @requires_invariants
    def capture_pre_allocation_field(self, tokens: list, schema_fields: list, is_noise: bool = False, domain: str = "") -> int:
        """Capture pre-allocation conflict topology from tokens with Relational Recall (Phase 31)."""
        with self.transaction("pre_allocation_capture"):
            from app.failure_injector import get_injector
            get_injector().inject("capture_pre_allocation_field")
            
            from app.field_laws import ROLE_EXCLUSIVITY
            captured = 0
            value_roles: Dict[str, List[str]] = {}
            for t in tokens:
                if not t.raw or not t.source_field:
                    continue
                if t.raw not in value_roles:
                    value_roles[t.raw] = []
                value_roles[t.raw].append(t.source_field)

            # Expand single tokens against schema exclusivity
            for t in tokens:
                if not t.raw:
                    continue
                src = t.source_field if t.source_field else (schema_fields[0] if schema_fields else '')
                if t.raw in value_roles and len(value_roles[t.raw]) >= 2:
                    continue
                for ra, rb in ROLE_EXCLUSIVITY:
                    if src in (ra, rb):
                        other = rb if src == ra else ra
                        fnames = set(t.source_field for t in tokens if t.source_field)
                        if other not in fnames:
                            if t.raw not in value_roles: value_roles[t.raw] = []
                            if src not in value_roles[t.raw]: value_roles[t.raw].append(src)
                            if other not in value_roles[t.raw]: value_roles[t.raw].append(other)

            # ─── Relational Recall (Phase 31) ───
            # Identify tokens that exist in 'crystalline' knowledge to stabilize new basins
            knowledge_boost = {}
            current_idx = self.metrics.total_records_processed
            for t in tokens:
                if not t.raw: continue
                # Temporal Manifold Weighting: newer matches give more boost
                boost = self._history.find_crystalline_matches(t.raw, current_record=current_idx)
                if boost > 0:
                    # Semantic Anchoring: stable knowledge reduces initial instability
                    knowledge_boost[t.raw] = min(0.3, boost * 0.2)

            # Track which tokens already have assigned basins
            tokens_with_basins = set()

            # Create field regions from schema field pairs
            view = self._topology.get_view()
            for t in tokens:
                if not t.raw:
                    continue
                if len(schema_fields) >= 2:
                    for i in range(len(schema_fields)):
                        for j in range(i + 1, len(schema_fields)):
                            sorted_roles = tuple(sorted([schema_fields[i], schema_fields[j]]))
                            existing_region = view.find_by_token_and_roles(t.raw, sorted_roles)
                            if existing_region:
                                tokens_with_basins.add(t.raw)
                                continue
                            
                            # Apply Relational Recall boost
                            initial_u = 0.2 - knowledge_boost.get(t.raw, 0.0)
                            region = FieldConflictRegion(
                                competing_roles=[schema_fields[i], schema_fields[j]],
                                token=t.raw,
                                instability=max(0.01, initial_u),
                                stability_momentum=0.6 if t.raw in knowledge_boost else 0.5,
                                semantic_pressure=self.metrics.field_pressure,
                                recurrence_score=0.0,
                                topology_neighbors=schema_fields,
                                domain=domain,
                            )
                            self._topology.append_region(region)
                            captured += 1
                            tokens_with_basins.add(t.raw)

            for token_val, roles in value_roles.items():
                if len(roles) < 2:
                    continue
                for i in range(len(roles)):
                    for j in range(i + 1, len(roles)):
                        pair = (roles[i], roles[j])
                        rev_pair = (roles[j], roles[i])
                        if pair in ROLE_EXCLUSIVITY or rev_pair in ROLE_EXCLUSIVITY:
                            sorted_roles = tuple(sorted([roles[i], roles[j]]))
                            region_id = self._topology.find_region_for_mutation(token_val, sorted_roles)
                            if region_id:
                                self._topology.update_region_after_recurrence(region_id, self.metrics.field_pressure)
                                if token_val in knowledge_boost:
                                    self._topology.adjust_region_instability(region_id, -0.05)
                            else:
                                # Apply Relational Recall to new contradiction basins
                                initial_u = 0.5 - knowledge_boost.get(token_val, 0.0)
                                region = FieldConflictRegion(
                                    competing_roles=[roles[i], roles[j]],
                                    token=token_val,
                                    instability=max(0.01, initial_u),
                                    stability_momentum=0.6 if token_val in knowledge_boost else 0.5,
                                    semantic_pressure=self.metrics.field_pressure,
                                    recurrence_score=self.learned_exclusions.get(sorted_roles, 0.0),
                                    topology_neighbors=list(set(roles)),
                                    domain=domain,
                                )
                                self._topology.append_region(region)
                            captured += 1
                            tokens_with_basins.add(token_val)
                            self.field_activation_count += 1

            # Create _unidentified basins for tokens not matching any schema field
            for t in tokens:
                if not t.raw:
                    continue
                if t.raw in value_roles and len(value_roles[t.raw]) >= 2:
                    continue
                
                # ONLY if this token hasn't been captured by any formal schema logic
                if t.raw not in tokens_with_basins:
                    # ─── Predictive Basin Pre-Heating (Phase 34) ───
                    # Suggest a specific hypo role based on type-manifold proximity
                    hypo_roles = ["_unidentified"]
                    from app.topological_query import get_tql_engine
                    tql = get_tql_engine(ws=self)
                    
                    # Find roles geometrically near this token's type
                    nearby = tql.find_roles_near_type(t.primary_type, radius=0.4)
                    if nearby:
                        schema_set = set(schema_fields)
                        # Add top candidates that are NOT in the active schema
                        candidates = [r["role"] for r in nearby 
                                     if r["role"] not in schema_set]
                        hypo_roles.extend(candidates[:2])
                    
                    sorted_roles = tuple(sorted(hypo_roles))
                    region_id = self._topology.find_region_for_mutation(t.raw, sorted_roles)
                    if region_id:
                        self._topology.adjust_region_recurrence(region_id, 0.1)
                    else:
                        region = FieldConflictRegion(
                            competing_roles=list(hypo_roles),
                            token=t.raw,
                            instability=0.4, # Pre-heated: lower than 0.5 default
                            domain=domain,
                        )
                        self._topology.append_region(region)
                    captured += 1

            # Prune old regions
            if self._topology.region_count() > 100:
                self._topology.trim(100, 50)
            return captured

    @requires_invariants
    def redistribute_instability(self):
        self._topology.redistribute_instability()

    @requires_invariants
    def aggregate_from_regions(self):
        if self._topology.region_count() == 0:
            self._energy.set_convergence(self._energy.convergence)
            return
        self._energy.update_from_regions(list(self._topology.iterate_regions()))

    @requires_invariants
    def decay_field_regions(self):
        """Each basin evolves autonomously.
        
        Exclusion effects returned by evolve() are applied through formal state APIs.
        """
        self._topology.evolve_all(ws=self, force=True)

    def snapshot(self, label: str = ""):
        """Record a compact topology snapshot for replay/debugging."""
        self._history.add_snapshot({
            "label": label,
            "time": self.metrics.total_records_processed,
            "energy": self.metrics.global_energy,
            "uncertainty": self.metrics.average_uncertainty,
            "field_pressure": self.metrics.field_pressure,
            "exclusions": len(self.learned_exclusions),
            "compatibilities": len(self.role_compatibility),
            "motifs": len(self.motif_counts),
        })
        self._history.trim_snapshots(max_size=500, keep=250)

    def replay(self) -> list:
        """Return topology evolution as a sequence of snapshots for replay."""
        return self._history.get_snapshots()

    def trace_waves(self) -> list:
        """Return propagation wave entries from snapshots for wave tracing."""
        return self._history.get_wave_snapshots()

    def diff_snapshots(self, idx_a: int = -2, idx_b: int = -1) -> dict:
        """Return the diff between two snapshots for causal chain inspection."""
        return self._history.diff_snapshots(idx_a, idx_b)

    def multi_scale_regions(self) -> dict:
        """Group field regions into larger-scale meta-basins.

        Micro: individual field regions (existing)
        Meso: regions that share competing roles (clusters)
        Macro: all regions aggregated (global summary)

        This enables cross-scale emergence — behavior at one scale
        can influence structure at adjacent scales.
        """
        view = self._topology.get_view()
        regions = view.all_regions()

        micro = [{"token": r.token, "roles": list(r.competing_roles),
                   "instability": round(r.instability, 3),
                   "convergence": round(r.local_convergence, 3)}
                  for r in regions]

        # Meso: cluster regions by shared roles
        meso = []
        assigned = set()
        for i in range(len(regions)):
            if i in assigned:
                continue
            cluster = [i]
            for j in range(i + 1, len(regions)):
                if j in assigned:
                    continue
                shared = set(regions[i].competing_roles) & set(regions[j].competing_roles)
                if shared:
                    cluster.append(j)
                    assigned.add(j)
            assigned.add(i)
            if len(cluster) > 1:
                cluster_regions = [regions[k] for k in cluster]
                meso.append({
                    "size": len(cluster),
                    "avg_instability": round(sum(r.instability for r in cluster_regions) / len(cluster_regions), 3),
                    "avg_convergence": round(sum(r.local_convergence for r in cluster_regions) / len(cluster_regions), 3),
                    "tokens": list(set(r.token for r in cluster_regions)),
                })

        # Macro: global aggregate
        macro = {
            "total_regions": view.region_count(),
            "meso_clusters": len(meso),
            "field_pressure": round(self.metrics.field_pressure, 3),
            "convergence": round(self.metrics.convergence_score, 3),
        }

        return {"micro": micro, "meso": meso, "macro": macro}

    def local_view(self, role: str) -> dict:
        """Local-only view — a role sees only its neighbors, not the full field.

        This enforces locality: no system should access global state directly.
        Each role sees:
        - its own compatibility mappings
        - exclusions for role pairs it participates in
        - field regions it's involved in
        - neighboring roles (from exclusivity edges)
        """
        from app.field_laws import ROLE_EXCLUSIVITY
        neighbors = set()
        for ra, rb in ROLE_EXCLUSIVITY:
            if role == ra:
                neighbors.add(rb)
            elif role == rb:
                neighbors.add(ra)
        local_exclusions = {
            k: v for k, v in self.learned_exclusions.items()
            if role in k
        }
        view = self._topology.get_view()
        local_regions = view.get_regions_for_role(role)
        local_compat = {
            k: v for k, v in self.role_compatibility.items()
            if k[0] == role
        }
        return {
            "role": role,
            "neighbors": list(neighbors),
            "local_exclusions": local_exclusions,
            "local_regions": len(local_regions),
            "local_compatibilities": len(local_compat),
        }

    def trace_field_evolution(self, token: str = "") -> dict:
        """Reconstruct the causal chain of field state evolution.

        If a token is specified, returns only lineage for that token.
        Otherwise returns the full field evolution summary with
        regions grouped by conflicting token.
        """
        view = self._topology.get_view()
        chain = {
            "regions": view.region_count(),
            "activations": self.field_activation_count,
            "current_pressure": self.metrics.field_pressure,
            "topology_density": self.topology_density,
            "exclusion_count": len(self.learned_exclusions),
            "wave_events": len(self.trace_waves()),
        }
        if token:
            chain["lineage"] = [
                {
                    "roles": list(r.competing_roles),
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "persistence": round(r.persistence, 3),
                }
                for r in view.find_by_token(token)
            ]
        elif view.region_count() > 0:
            regions_by_token: dict = {}
            for r in view.all_regions():
                regions_by_token.setdefault(r.token, []).append({
                    "roles": list(r.competing_roles),
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "recurrence": round(r.recurrence_score, 3),
                    "persistence": round(r.persistence, 3),
                })
            chain["regions_by_token"] = regions_by_token
        return chain

    @requires_invariants
    def _synthesize_crystalline_record(self, record: dict, current_record: Optional[int] = None):
        """Synthesize a high-integrity knowledge record with temporal awareness."""
        idx = current_record if current_record is not None else self.metrics.total_records_processed
        self._history.synthesize_crystalline(record, idx)

    @requires_invariants
    def induce_topological_laws(self):
        self._topology.induce_topological_laws(self.learned_exclusions)

    @requires_invariants
    def observe_field_perturbation(self, output: dict, tokens: list):
        from app.instability_api import get_immune_system
        immune = get_immune_system(ws=self)
        
        # Source identification
        source = output.get("source_url", "unknown_source")
        
        from app.field_laws import ROLE_EXCLUSIVITY
        alloc_conflicts = output.get("_allocation_conflicts", [])
        
        # ─── Semantic Immunity (Phase 42) ───
        # Check if source is allowed to perturb the field
        contested_roles = [fc.get("role", "") for fc in alloc_conflicts]
        if not immune.validate_perturbation(source, "various", contested_roles):
            self._observability.emit_telemetry("immunity_block", {"source": source})
            return
            
        for fc in alloc_conflicts:
            role = fc.get("role", "")
            candidate = fc.get("candidate", "")
            for ra, rb in ROLE_EXCLUSIVITY:
                if role == ra:
                    peer = rb
                elif role == rb:
                    peer = ra
                else:
                    continue
                if candidate:
                    key = tuple(sorted([role, peer]))
                    current = self._instability.get_exclusion(role, peer)
                    self._instability.set_exclusion(key, current + 0.1)

                    # Emit Telemetry (Phase 41)
                    self._observability.emit_telemetry("allocation_conflict", {
                        "role": role,
                        "peer": peer,
                        "candidate": candidate,
                        "new_exclusion": current + 0.1
                    })
        # Inlined from the former instability_state.observe_field_perturbation
        all_exclusions = set(ROLE_EXCLUSIVITY)
        for (r1, r2), strength in self.learned_exclusions.items():
            if strength > 0.3:
                all_exclusions.add(tuple(sorted([r1, r2])))

        contested_tokens = set()
        for fc in alloc_conflicts:
            if fc.get("candidate"):
                contested_tokens.add(fc["candidate"])
        view = self._topology.get_view()
        for r in view.all_regions():
            if r.token not in contested_tokens:
                contested_tokens.add(r.token)

        for token_val in contested_tokens:
            exclusive_roles = []
            for r in view.find_by_token(token_val):
                for role in r.competing_roles:
                    if role not in exclusive_roles:
                        exclusive_roles.append(role)
            sr = tuple(sorted(exclusive_roles))
            for i in range(len(sr)):
                for j in range(i + 1, len(sr)):
                    pair = tuple(sorted([sr[i], sr[j]]))
                    if pair in all_exclusions:
                        if sr[i] not in exclusive_roles:
                            exclusive_roles.append(sr[i])
                        if sr[j] not in exclusive_roles:
                            exclusive_roles.append(sr[j])
            if len(exclusive_roles) < 2:
                continue
            existing = self._topology.find_region_for_mutation(token_val, tuple(sorted(exclusive_roles)))
            if existing:
                self._topology.adjust_region_recurrence(existing, 0.05)
            else:
                new_region = FieldConflictRegion(
                    token=token_val,
                    competing_roles=list(exclusive_roles),
                    instability=0.6,
                )
                self._topology.append_region(new_region)

    def detect_communities(self):
        self._topology.detect_communities()

    @requires_invariants
    def evolve_macro_state(self):
        with self.transaction("macro_evolution"):
            if self._topology.region_count() > 0:
                regions = list(self._topology.iterate_regions())
                self._energy.evolve_from_regions(regions, len(regions))
                self._energy.set_exclusion_count(len(self.learned_exclusions))
                prune_threshold = 0.05 + self._energy.global_entropy * 0.3
                self._topology.filter_regions(lambda r: r.instability > prune_threshold or r.local_energy > 0.1)
                
                # Accumulate Stability Debt if energy is trapped (Law 4)
                if self.metrics.global_energy > 7.0 and self.metrics.convergence_score < 0.4:
                    self._energy.adjust_stability_debt(0.1)
                    
            self._topology.decay_topological_laws()
            for (r1, r2), val in self.learned_exclusions.items():
                self._topology.update_schema_patterns((r1, r2), val)
                # Promote extremely stable exclusions to Anchors
                if val > 0.9 and self._topology.topological_laws.get((r1, r2), 0) > 0.8:
                    self._topology.record_anchor((r1, r2))
                    
            self._topology.detect_communities()
            # ─── Semantic Sharding (Phase 35) ───
            self._manifold.shard_manifold(self._topology.global_communities)
            self._manifold.rebalance_shards(max_shard_size=50)
            
            self._self_heal_topology()
            self._re_seed_unstable_roles()
            self._spawn_hypo_roles()
            self._promote_stable_hypotheses()
            self._forecast_causal_needs()
            
            # ─── Health Guardians (Phase 41) ───
            health = self.get_cognitive_health()
            if health["system_energy"] > 8.0:
                self._observability.emit_telemetry("health_alert", {
                    "reason": "critical_energy",
                    "value": health["system_energy"]
                })
                logging.getLogger(__name__).warning("COGNITIVE HEALTH ALERT: Critical Energy Level Detected")
                
            if health["certainty"] < 0.1:
                self._observability.emit_telemetry("health_alert", {
                    "reason": "manifold_collapse",
                    "value": health["certainty"]
                })
                logging.getLogger(__name__).warning("COGNITIVE HEALTH ALERT: Manifold Resolution Collapse")

            # ─── Immune Response Cascades (Phase 42) ───
            # Identify corrupted anchored roles (high instability)
            for role in self._manifold.role_anchors:
                instability = self.metrics.schema_instability.get(role, 0.0)
                if instability > 0.8:
                    # Corruption detected: attempt re-seeding from seed type
                    from app.semantic_allocation_engine import _infer_role_type
                    from app.semantic_inference_engine import RoleEmbeddingEngine
                    reng = RoleEmbeddingEngine()
                    
                    seed_type = _infer_role_type(role)
                    seed_vec = reng._get_type_vector(seed_type)
                    
                    self._manifold.set_manifold_vector(role, seed_vec)
                    self._energy.set_schema_instability(role, 0.5) # Reset to neutral
                    
                    self._observability.emit_telemetry("immune_recovery", {
                        "role": role,
                        "reason": "high_instability_anchor"
                    })
                    logging.getLogger(__name__).info(f"IMMUNE RESPONSE: Recovered corrupted anchor role [{role}]")
            
            # Trigger Phase Transition if debt threshold reached
            if self.metrics.stability_debt > 1.0:
                self.trigger_phase_transition()

    def _promote_stable_hypotheses(self):
        """Promote hypothetical roles to the active schema if they stabilize (Phase 29)."""
        for role in self._manifold.get_manifold_roles():
            if role.startswith("hypo_"):
                instability = self._energy.get_schema_instability(role)
                # Success criteria: Very low instability in the hypothetical role
                if instability < 0.2:
                    clean_name = role[5:] # Remove 'hypo_'
                    self._evolved_schema.add(clean_name)
                    # Migrate manifold vector to new role
                    vec = self._manifold.get_manifold_vector(role)
                    self._manifold.set_manifold_vector(clean_name, vec)
                    # Clear hypo role
                    self._manifold.remove_manifold_role(role)
                    self._energy.set_schema_instability(role, 0.5) # Reset
                    logging.getLogger(__name__).info(f"DYNAMIC SCHEMA EXPANSION: Promoted {role} to active role: {clean_name}")
                    self.record_delta("global", "promote_hypo", {"hypo": role, "active": clean_name})

    @property
    def evolved_schema(self) -> List[str]:
        return list(self._evolved_schema)

    def trigger_phase_transition(self):
        """Sudden restructuring of the field geometry to escape local minima (Law 4)."""
        logging.getLogger(__name__).info("METASTABILITY TRIGGERED: Executing Phase Transition.")
        with self.transaction("phase_transition"):
            # 1. Sudden Relaxation of all non-anchored exclusions (Melting)
            anchors = self._topology.anchors
            for key in list(self.learned_exclusions.keys()):
                if key not in anchors:
                    current = self._instability.get_exclusion_by_key(key)
                    self._instability.set_exclusion(key, current * 0.2)
            
            # 2. Perturb manifold positions for non-anchored roles
            try:
                from app.semantic_inference_engine import RoleEmbeddingEngine
                reng = RoleEmbeddingEngine()
                anchored_roles = set()
                for a, b in anchors:
                    anchored_roles.add(a); anchored_roles.add(b)
                    
                import random
                for role in reng.manifold.keys():
                    if role not in anchored_roles:
                        noise = [random.uniform(-0.1, 0.1) for _ in range(16)]
                        self._manifold.apply_force_to_manifold(role, noise)
            except Exception as e:
                logging.getLogger(__name__).warning("Manifold perturbation failed: %s", e)
                
            # 3. Reset debt
            self._energy.stability_debt = 0.0
            self.record_delta("global", "phase_transition", {
                "debt_cleared": 1.0,
                "anchors_preserved": len(anchors)
            })

    def _forecast_causal_needs(self):
        """Forecast future schema needs from emerging motifs."""
        current = self.metrics.total_records_processed
        forecast = self._motif.predict_future_motifs(current)
        for motif in forecast:
            logging.getLogger(__name__).info(f"Causal Forecast: emerging schema motif detected: {motif}")

    def _self_heal_topology(self):
        """Detect and resolve impossible topological law combinations."""
        laws = self.topological_laws
        exclusions = self.learned_exclusions
        self._topology.clear_impossible_neighborhoods()

        for key, law_val in laws.items():
            exclusion_val = exclusions.get(key, 0.0)
            # Structural Contradiction: Strong proximity law vs Strong exclusion
            if law_val > 0.4 and exclusion_val > 0.4:
                self._topology.add_impossible_neighborhood(set(key))
                
                # Thermodynamic Resolution: the stronger signal wins, the weaker is eroded
                if law_val >= exclusion_val:
                    # Law is stronger: erode exclusion
                    current = self._instability.get_exclusion_by_key(key)
                    self._instability.set_exclusion(key, current * 0.5)
                else:
                    # Exclusion is stronger: erode law
                    self._topology.set_topological_law(key, law_val * 0.5)

    def _re_seed_unstable_roles(self):
        communities = self.global_communities
        if not communities:
            for (ra, rb), cohesion in self.neighborhood_cohesion.items():
                if cohesion > 0.6:
                    communities = [{ra, rb}]
                    break
        if not communities:
            return
        for community in communities:
            stable_members = [m for m in community if self._energy.get_schema_instability(m) < 0.2]
            unstable_members = [m for m in community if self._energy.get_schema_instability(m) >= 0.5]
            if not stable_members or not unstable_members:
                continue
            
            # Community Consensus: Average of all stable members
            consensus_vec = [0.0] * 16
            for stable in stable_members:
                vec = self._manifold.get_manifold_vector(stable) or [0.5]*16
                for i in range(16):
                    consensus_vec[i] += vec[i]
            for i in range(16):
                consensus_vec[i] /= len(stable_members)

            for role in unstable_members:
                # Use controlled blend through ManifoldState
                self._manifold.blend_manifold_vector(role, consensus_vec, alpha=0.6, beta=0.4)
                self._energy.set_schema_instability(role, 0.4)

    def _spawn_hypo_roles(self):
        for region in self._topology.iterate_regions():
            if "_unidentified" in region.competing_roles and region.integrity > 0.5 and region.recurrence_score > 0.3:
                hypo_role = f"hypo_{region.token.lower().replace(' ', '_')}"
                if not self._manifold.has_manifold_role(hypo_role):
                    # Use controlled manifold mutation
                    self._manifold.set_manifold_vector(hypo_role, [0.5] * 16)
                    self._energy.set_schema_instability(hypo_role, 0.5)

    def topological_search(self, query: str) -> list:
        return self._history.topological_search(query)

    def execute_tql(self, query: str) -> dict:
        """Execute a Topological Query Language (TQL) expression."""
        from app.topological_query import get_tql_engine
        return get_tql_engine(ws=self).execute_tql(query)

    def get_crystalline_attractors(self, token_vals=None) -> list:
        return self._history.get_crystalline_attractors(token_vals)

    def get_system_pressure(self) -> float:
        """Composite pressure metric for adaptive throttling (Phase 33)."""
        health = self.get_cognitive_health()
        # High fragmentation or high energy increases pressure
        # High certainty decreases pressure
        pressure = (health["system_energy"] / 10.0 + health["fragmentation"]) - health["certainty"] * 0.5
        return max(0.1, min(2.0, pressure))

    @requires_invariants
    def relax_topology(self, budget: Optional[Any] = None):
        """Gradual erosion of weak structures."""
        from app.runtime_budget import get_default_budget
        b = budget or get_default_budget()
        
        with self.transaction("relaxation"):
            self._instability.decay(rate=0.05)
            self._topology.decay_topological_laws()
            # Decay weak compatibilities (below 0.5 drift toward 0)
            for key in list(self.role_compatibility.keys()):
                if not b.increment_cycle():
                    break
                val = self.role_compatibility.get(key, 0.5)
                if val < 0.5:
                    new_val = max(0.0, val - 0.01)
                    if new_val <= 0.0:
                        self._manifold.clear_compatibility_for_key(key)
                    else:
                        self._manifold.set_compatibility(key[0], key[1] if len(key) > 1 else "unknown", new_val)
            self._motif.prune_weak(threshold=0.1)
            pruned_regions = self._topology.garbage_collect(max_idle=20)
            pruned_roles = self._manifold.prune_manifold(self.metrics.schema_instability, threshold=0.9)
            distilled_atoms = self._topology.distill_crystalline_atoms()
            try:
                from app.semantic_inference_engine import RoleEmbeddingEngine
                reng = RoleEmbeddingEngine()

                # Snapshot before relaxation for drift tracking
                before_manifold = {k: list(v) for k, v in self.role_manifold.items()}

                reng.relax_manifold()

                # Log drift for active roles (Phase 41)
                for role, v_after in self.role_manifold.items():
                    v_before = before_manifold.get(role)
                    if v_before:
                        drift = sum((a - b)**2 for a, b in zip(v_before, v_after))**0.5
                        if drift > 0.001:
                            self._observability.log_drift(role, drift)

                self._observability.emit_telemetry("manifold_relaxation", {
                    "role_count": len(self.role_manifold),
                    "active_drift": len([r for r in self.role_manifold if r in before_manifold])
                })

            except Exception as e:

                logging.getLogger(__name__).warning(
                    "RoleEmbeddingEngine.relax_manifold failed in relax_topology: %s", e
                )
            self.record_delta("global", "relax_topology", {
                "budget": b.usage_report,
                "regions_pruned": pruned_regions,
                "roles_pruned": pruned_roles,
                "atoms_distilled": distilled_atoms
            })
            return 0

    @requires_invariants
    def dream(self, cycles: int = 1, budget: Optional[Any] = None) -> dict:
        dreams = []
        from app.runtime_budget import CognitiveBudget
        
        pressure = self.get_system_pressure()
        # High pressure reduces time budget to ensure node responsiveness (Phase 33)
        max_time = 500.0 / pressure
        b = budget or CognitiveBudget(max_cycles=cycles * 10, max_time_ms=max_time)
        
        with self.transaction("dreaming"):
            for _ in range(cycles):
                if not b.increment_cycle():
                    break
                    
                self._topology.evolve_all(ws=self)
                self.relax_topology(budget=b)
                self.evolve_macro_state()
                for region in self._topology.iterate_regions():
                    if region.instability > 0.6 and region.recurrence_score > 0.5:
                        key = tuple(sorted(region.competing_roles))
                        current = self._instability.get_exclusion_by_key(key)
                        self._instability.set_exclusion(key, current + 0.05)
                        dreams.append({
                            "type": "exclusion",
                            "roles": region.competing_roles,
                            "token": region.token,
                        })
            self._topology.update_local_memory_from_instability()
            self.record_delta("global", "dream", {
                "requested_cycles": cycles, 
                "actual_cycles": b.cycle_count,
                "dreams_count": len(dreams),
                "budget": b.usage_report
            })
        return {
            "dreams": dreams, 
            "status": "converging" if not dreams else "learning",
            "budget_exhausted": b.is_exhausted
        }

    @requires_invariants
    def update_scale_coupling(self) -> int:
        """Couple regions through shared roles — all region mutations routed through TopologyState."""
        if self._topology.region_count() < 2:
            return 0
        pressure = self.metrics.field_pressure
        hot_neighborhoods = 0
        self._total_energy_before = sum(r.local_energy for r in self._topology.iterate_regions()) if self._topology.region_count() > 0 else 0.0
        role_map: dict = {}
        for r in self._topology.iterate_regions():
            for role in r.competing_roles:
                role_map.setdefault(role, []).append(r)
        for r in self._topology.iterate_regions():
            peers_map = {}
            for role in r.competing_roles:
                for peer in role_map.get(role, []):
                    if peer.region_id != r.region_id:
                        # Domain isolation: only couple regions from same domain
                        if r.domain and peer.domain and r.domain != peer.domain:
                            continue
                        peers_map[peer.region_id] = peer
            peers = list(peers_map.values())
            if not peers:
                continue
            avg_u = sum(p.instability for p in peers) / len(peers)
            avg_c = sum(p.integrity for p in peers) / len(peers)
            coupling = 0.05 * (0.5 + pressure)
            self._topology.set_region_temperature(r.region_id, r.local_temperature * 0.98 + (avg_u * 0.4) * 0.02)
            u_gap = avg_u - r.instability
            self._topology.adjust_region_instability(r.region_id, u_gap * coupling * avg_c)
            self._topology.set_region_integrity(r.region_id, r.integrity * 0.9 + avg_c * 0.1)
            avg_e = sum(p.local_energy for p in peers) / len(peers)
            e_gap = avg_e - r.local_energy
            transfer = e_gap * coupling * 0.5
            self._topology.adjust_region_energy(r.region_id, transfer)
            self._topology.set_region_instability(r.region_id, r.instability + e_gap * 0.1 * coupling)
            if avg_u > 0.3:
                hot_neighborhoods += 1
        if self._topology.region_count() > 0:
            total = sum(r.local_energy for r in self._topology.iterate_regions())
            target = getattr(self, '_total_energy_before', total)
            if total > 0 and abs(total - target) / max(target, 0.001) > 0.001:
                scale = target / total
                for r in self._topology.iterate_regions():
                    self._topology.set_region_energy(r.region_id, r.local_energy * scale)
        return hot_neighborhoods

    def dispatch_actions(self) -> int:
        """Trigger autonomous actions based on manifold convergence (Phase 43)."""
        triggered = 0
        active_actions = self._action.active_actions
        if not active_actions:
            return 0
            
        from app.policy_engine import get_policy_engine
        from app.llm_bridge import get_plugin_manager
        policy = get_policy_engine(ws=self)
        plugins = get_plugin_manager(ws=self)
        pressure = self.get_system_pressure()
        
        with self.transaction("action_dispatch"):
            for region in self._topology.iterate_regions():
                # Only check stable basins (low instability)
                if region.instability < 0.3:
                    for role in region.competing_roles:
                        if not policy.can_dispatch_action(role, pressure):
                            continue
                            
                        role_vec = self._manifold.get_manifold_vector(role)
                        if not role_vec:
                            continue
                            
                        for aid, details in active_actions.items():
                            target_vec = details["target_vec"]
                            threshold = details["threshold"]
                            handler_name = details["handler_name"]
                            
                            # Euclidean distance in manifold
                            dist = sum((a - b)**2 for a, b in zip(role_vec, target_vec))**0.5
                            
                            if dist < threshold:
                                # ACTION TRIGGERED
                                logging.getLogger(__name__).info(
                                    f"AGENCY TRIGGERED: Role [{role}] activated Action [{aid}] (Dist: {dist:.4f})"
                                )
                                
                                # ─── Tool Calling (Phase 43) ───
                                # Attempt to call actual plugin handler
                                success = True
                                tool_result = None
                                try:
                                    tool_result = plugins.call_tool(handler_name, role=role, token=region.token)
                                except Exception as e:
                                    logging.getLogger(__name__).warning(f"Plugin execution failed for {handler_name}: {e}")
                                    success = False

                                self._action.log_execution(aid, success=success, details={
                                    "role": role,
                                    "token": region.token,
                                    "distance": dist,
                                    "tool_result": str(tool_result)[:100] if tool_result else None
                                })
                                triggered += 1
                                # Reinforce this role's alignment as a reward
                                if success:
                                    self._manifold.blend_manifold_vector(role, target_vec, alpha=0.95, beta=0.05)
            
            if triggered > 0:
                self.record_delta("global", "dispatch_actions", {"count": triggered})
                
        return triggered

    def synthesize_hierarchical_envelopes(self):
        """Distill stable role communities into higher-order envelopes (Phase 38)."""
        communities = self._topology.global_communities
        if not communities:
            return
            
        with self.transaction("hierarchical_synthesis"):
            for idx, community in enumerate(communities):
                if len(community) < 2:
                    continue
                    
                # Check stability of the community (mean instability)
                total_instability = 0.0
                for role in community:
                    total_instability += self.metrics.schema_instability.get(role, 0.5)
                avg_instability = total_instability / len(community)
                
                # Only distill stable clusters (Phase 38 threshold: < 0.2)
                if avg_instability < 0.2:
                    envelope_id = f"env_{idx}_{int(time.time())}"
                    
                    # Compute centroid vector for the envelope
                    constituents = list(community)
                    vectors = [self._manifold.get_manifold_vector(r) for r in constituents]
                    vectors = [v for v in vectors if v]
                    if not vectors:
                        continue
                        
                    dim = len(vectors[0])
                    centroid = [0.0] * dim
                    for v in vectors:
                        for k in range(dim):
                            centroid[k] += v[k]
                    centroid = [c / len(vectors) for c in centroid]
                    
                    # Create the envelope
                    self._abstraction.create_envelope(envelope_id, constituents, centroid, level=1)
                    # Register the envelope itself in the manifold
                    self._manifold.set_manifold_vector(envelope_id, centroid)
                    self._manifold.anchor_role(envelope_id) # Protect higher-order concepts
                    
                    logging.getLogger(__name__).info(
                        f"HIERARCHICAL SYNTHESIS: Distilled community {constituents} into Envelope [{envelope_id}]"
                    )

    def evaluate_topological_consistency(self) -> dict:
        """Evaluate the manifold's logical consistency (Meta-Reasoning - Phase 38)."""
        envelopes = self._abstraction.envelopes
        contradictions = []
        
        for eid, details in envelopes.items():
            constituents = list(details["constituents"])
            if len(constituents) < 2:
                continue
                
            # Check for mutual repulsion within the envelope
            for i in range(len(constituents)):
                for j in range(i + 1, len(constituents)):
                    r1, r2 = constituents[i], constituents[j]
                    exclusion = self._instability.get_exclusion(r1, r2)
                    
                    # If constituents strongly repel each other, the envelope is contradictory
                    if exclusion > 0.7:
                        contradictions.append({
                            "envelope": eid,
                            "pair": (r1, r2),
                            "exclusion": exclusion,
                            "type": "internal_repulsion"
                        })
        
        consistency_score = 1.0 - (len(contradictions) / max(len(envelopes), 1))
        
        if contradictions:
            self.record_delta("global", "meta_reasoning", {
                "consistency_score": consistency_score,
                "contradiction_count": len(contradictions)
            })
            
        return {
            "score": consistency_score,
            "contradictions": contradictions
        }

    def merge_hierarchical_knowledge(self, other_abstraction: dict):
        """Merge hierarchical abstractions from another node (Phase 38)."""
        remote_envelopes = other_abstraction.get("envelopes", {})
        if not remote_envelopes:
            return
            
        with self.transaction("hierarchical_merge"):
            local_envelopes = self._abstraction.envelopes
            
            for rid, r_details in remote_envelopes.items():
                r_vec = r_details["manifold_vec"]
                
                # Search for a similar local envelope
                merged = False
                for lid, l_details in local_envelopes.items():
                    l_vec = l_details["manifold_vec"]
                    
                    # Manifold distance
                    dist = sum((a - b)**2 for a, b in zip(l_vec, r_vec))**0.5
                    
                    if dist < 0.15:
                        # Similar concept; merge constituents
                        new_constituents = set(l_details["constituents"]) | set(r_details["constituents"])
                        # Blend vectors
                        new_vec = [(a + b) / 2 for a, b in zip(l_vec, r_vec)]
                        
                        self._abstraction.create_envelope(lid, list(new_constituents), new_vec, level=max(l_details["level"], r_details["level"]))
                        self._manifold.set_manifold_vector(lid, new_vec)
                        
                        logging.getLogger(__name__).info(
                            f"HIERARCHICAL MERGE: Merged remote concept {rid} into local [{lid}] (Dist: {dist:.4f})"
                        )
                        merged = True
                        break
                
                if not merged:
                    # New concept; import it
                    self._abstraction.create_envelope(rid, r_details["constituents"], r_vec, level=r_details["level"])
                    self._manifold.set_manifold_vector(rid, r_vec)
                    self._manifold.anchor_role(rid)

    @property
    def node_id(self) -> str:
        return self._node_id

    @node_id.setter
    def node_id(self, value: str):
        self._node_id = value
        if hasattr(self, '_vector_clock'):
            self._vector_clock.node_id = value

    def clear(self):
        self._energy.clear()
        self._topology.clear()
        self._instability.clear()
        self._manifold.clear()
        self._motif.clear()
        self._transition.clear()
        self._intent.clear()
        self._action.clear()
        self._abstraction.clear()
        self._observability.clear()
        self._history.clear()
        self._current_journal = []
        self._global_journal = []
        self._scheduler.clear()
        self.last_update_time = time.time()

    # ─── Garbage Collection Gateway APIs ────────────────────────────────
    # These encapsulate all GC operations so topology_gc.py never needs
    # to access sub-states directly — strengthening the ownership boundary.

    def gc_collect_stale_regions(self, min_instability: float = 0.02, min_energy: float = 0.5) -> int:
        """Remove field regions below thresholds. Returns count removed."""
        before = self._topology.region_count()
        self._topology.filter_regions(
            lambda r: r.instability > min_instability or r.local_energy > min_energy
        )
        return before - self._topology.region_count()

    def gc_collect_stale_motifs(self, threshold: float = 0.05) -> int:
        """Remove motifs that have decayed below usefulness threshold. Returns count removed."""
        before = self._motif.count()
        self._motif.prune_weak(threshold=threshold)
        return before - self._motif.count()

    def gc_collect_stale_exclusions(self, threshold: float = 0.01) -> int:
        """Remove very weak exclusions. Returns count removed."""
        return self._instability.prune_exclusions_weak(threshold=threshold)

    def gc_trim_snapshots(self, max_size: int = 500, keep: int = 250) -> int:
        """Trim excess topology snapshots. Returns count removed."""
        before = len(self._history.get_snapshots())
        self._history.trim_snapshots(max_size=max_size, keep=keep)
        return before - len(self._history.get_snapshots())

    def gc_collect(self) -> dict:
        """Run full garbage collection cycle. Returns dict with counts per category."""
        return {
            "regions": self.gc_collect_stale_regions(),
            "motifs": self.gc_collect_stale_motifs(),
            "exclusions": self.gc_collect_stale_exclusions(),
            "snapshots": self.gc_trim_snapshots(),
        }

    def schedule_cognitive_task(self, task_id: str, priority: Any, 
                                handler: Callable, *args, **kwargs):
        """Register a task with the cognitive scheduler (Phase 40)."""
        self._scheduler.schedule(task_id, priority, handler, *args, **kwargs)

    def process_cognitive_queue(self, budget_ms: float = 100.0) -> int:
        """Execute scheduled tasks within the time budget."""
        return self._scheduler.step(budget_ms=budget_ms)

    def to_dict(self) -> dict:
        """Serialize state to a JSON-compatible dictionary."""
        last_trace = self._global_journal[-1].get("trace_id") if self._global_journal else None
        result = {
            "version": "5.0",
            "last_update": self.last_update_time,
            "node_id": self.node_id,
            "clock": self._vector_clock.to_dict(),
            "last_trace_id": last_trace,
            "parent_node_id": self._parent_node_id,
            "branch_label": self._branch_label
        }
        result.update(self._energy.to_dict())
        result.update(self._manifold.to_dict())
        result.update(self._motif.to_dict())
        result.update(self._transition.to_dict())
        result.update(self._history.to_dict())
        result.update(self._instability.to_dict())
        result.update(self._intent.to_dict())
        result.update(self._action.to_dict())
        result.update(self._abstraction.to_dict())
        result.update(self._observability.to_dict())
        result["topology"] = self._topology.to_dict()
        result["evolved_schema"] = list(self._evolved_schema)
        return result

    @requires_invariants
    def from_dict(self, data: dict):
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
        metrics_data = data.get("metrics", None)
        if metrics_data is not None:
            self._energy.load_from_dict(metrics_data)
        else:
            metric_keys = {"global_energy", "global_entropy", "exclusion_count",
                          "total_records_processed", "cumulative_density", 
                          "cumulative_uncertainty", "dataset_coherence", 
                          "_convergence", "_temperature", "_integrity", 
                          "stability_debt", "schema_instability"}
            flat_metrics = {k: v for k, v in data.items() if k in metric_keys}
            if flat_metrics:
                self._energy.load_from_dict(flat_metrics)
                
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
            self._instability.load_from_dict(excl_data)
            
        # Load TopologyState
        topo_data = data.get("topology")
        if topo_data:
            self._topology.from_dict(topo_data)
        
        self._evolved_schema = set(data.get("evolved_schema", []))
        self.last_update_time = data.get("last_update", time.time())
        self._last_trace_id = data.get("last_trace_id")

    def mutation_diff(self, other: "SemanticWorldState") -> dict:
        """Compute a structural diff between two world states for observability."""
        diff: dict = {}
        if self.metrics.total_records_processed != other.metrics.total_records_processed:
            diff["records_processed"] = (self.metrics.total_records_processed, other.metrics.total_records_processed)
        if self.metrics.global_energy != other.metrics.global_energy:
            diff["global_energy"] = (self.metrics.global_energy, other.metrics.global_energy)
        if self.metrics.global_entropy != other.metrics.global_entropy:
            diff["global_entropy"] = (self.metrics.global_entropy, other.metrics.global_entropy)
        added_roles = set(other.role_compatibility) - set(self.role_compatibility)
        if added_roles:
            diff["added_role_compatibilities"] = {str(k): v for k, v in other.role_compatibility.items() if k in added_roles}
        changed_roles = {
            k for k in set(self.role_compatibility) & set(other.role_compatibility)
            if abs(self.role_compatibility[k] - other.role_compatibility[k]) > 0.01
        }
        if changed_roles:
            diff["changed_role_compatibilities"] = {str(k): (self.role_compatibility[k], other.role_compatibility[k]) for k in changed_roles}
        added_motifs = set(other.motif_counts) - set(self.motif_counts)
        if added_motifs:
            diff["added_motifs"] = [str(m) for m in added_motifs]
        new_exclusions = set(other.learned_exclusions) - set(self.learned_exclusions)
        if new_exclusions:
            diff["new_exclusions"] = [str(e) for e in new_exclusions]
        return diff

    def semantic_diff(self, other: "SemanticWorldState") -> dict:
        """Quantify geometric and topological divergence between states (Phase 39)."""
        divergence = {
            "manifold_drift": 0.0,
            "new_roles": [],
            "missing_roles": [],
            "tension_delta": 0.0,
        }
        
        # 1. Manifold Drift (Mean Euclidean distance)
        local_m = self._manifold.role_manifold
        other_m = other._manifold.role_manifold
        
        common_roles = set(local_m.keys()) & set(other_m.keys())
        if common_roles:
            total_dist = 0.0
            for r in common_roles:
                v1, v2 = local_m[r], other_m[r]
                dist = sum((a - b)**2 for a, b in zip(v1, v2))**0.5
                total_dist += dist
            divergence["manifold_drift"] = total_dist / len(common_roles)
            
        divergence["new_roles"] = list(set(other_m.keys()) - set(local_m.keys()))
        divergence["missing_roles"] = list(set(local_m.keys()) - set(other_m.keys()))
        
        # 2. Tension Delta
        divergence["tension_delta"] = abs(other.metrics.global_energy - self.metrics.global_energy)
        
        return divergence

    def merge_branch(self, branch: "SemanticWorldState", alpha: float = 0.5):
        """Merge an isolated branch back into the current state (Phase 39)."""
        with self.transaction(f"merge_branch:{branch.node_id}"):
            # 1. Manifold Merge (Linear blending of vectors)
            self._manifold.merge(branch._manifold.to_dict(), alpha=alpha)
            
            # 2. Instability Merge (Tension reconciliation)
            self._instability.merge(branch._instability.to_dict())
            
            # 3. Motif Merge
            self._motif.merge(branch._motif.to_dict())
            
            # 4. Abstraction Merge
            self.merge_hierarchical_knowledge(branch._abstraction.to_dict())
            
            # 5. Causal Lineage: update vector clock
            self._vector_clock.update(branch._vector_clock.get_clock())
            
            logging.getLogger(__name__).info(
                f"SUBSTRATE MERGED: [{branch.node_id}] -> [{self.node_id}] (Alpha: {alpha})"
            )


# Global Singleton
_world_state: Optional[SemanticWorldState] = None

def get_world_state() -> SemanticWorldState:
    global _world_state
    if _world_state is None:
        _world_state = SemanticWorldState()
    return _world_state
