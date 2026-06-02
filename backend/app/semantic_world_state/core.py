import logging
import time
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Set

from app.invariant_firewall import requires_invariants
from app.semantic_world_state.events import EventMixin
from app.semantic_world_state.locks import NonBlockingRLock
from app.semantic_world_state.memory import MemoryMixin
from app.semantic_world_state.metrics import MetricsMixin
from app.semantic_world_state.serialization import SerializationMixin
from app.semantic_world_state.topology import TopologyMixin
from app.transaction_context import active_transaction

logger = logging.getLogger(__name__)


class SemanticWorldState(EventMixin, MemoryMixin, SerializationMixin, MetricsMixin, TopologyMixin):
    """
    Canonical Semantic World State — now a true orchestrator.

    Meaning emerges from the relational topology of this state.
    No subsystem may maintain isolated semantic truth.
    """

    def __init__(self, node_id: Optional[str] = None):
        import uuid

        from app.abstraction_state import AbstractionState
        from app.action_state import ActionState
        from app.energy_state import EnergyState
        from app.graph_update_scheduler import GlobalCognitiveScheduler
        from app.history_state import HistoryState
        from app.instability_state import InstabilityState
        from app.intent_state import IntentState
        from app.manifold_state import ManifoldState
        from app.motif_state import MotifState
        from app.observability import ObservabilityState
        from app.topology_state import TopologyState
        from app.transition_state import TransitionState
        from app.vector_clock import VectorClock

        self._node_id = node_id or str(uuid.uuid4())[:8]
        self._vector_clock = VectorClock(self._node_id)
        self._lock = NonBlockingRLock()  # Reentrant lock for nested transactions

        self._topology = TopologyState(delta_callback=self.record_delta, read_callback=self.record_read)
        self._energy = EnergyState(delta_callback=self.record_delta)
        self._instability = InstabilityState(delta_callback=self.record_delta)
        self._manifold = ManifoldState(delta_callback=self.record_delta)
        self._motif = MotifState(delta_callback=self.record_delta)
        self._transition = TransitionState(delta_callback=self.record_delta)
        self._intent = IntentState(delta_callback=self.record_delta)
        self._action = ActionState(delta_callback=self.record_delta)
        self._abstraction = AbstractionState(delta_callback=self.record_delta)
        self._observability = ObservabilityState(delta_callback=self.record_delta)
        self._history = HistoryState(delta_callback=self.record_delta)

        # Isolated domain-specific state adapters (Phase 82 Decentralization)
        from app.crawl_state import get_crawl_state
        from app.regression_state import get_regression_state
        from app.telemetry_state import get_telemetry_state

        self.crawl = get_crawl_state()
        self.telemetry = get_telemetry_state()
        self.regression = get_regression_state()

        # Phase 83: Multi-Shard Federation Manager
        from app.federation_manager import FederationManager

        self.federation = FederationManager(self)

        # Phase 60 / 63: Drift Tracking References
        self._manifold._energy_ref = self._energy
        self._manifold._obs_ref = self._observability

        self._scheduler = GlobalCognitiveScheduler(ws=self)

        self.metrics = self._energy
        self.last_update_time: float = time.time()
        self._transaction_depth = 0
        self._replaying = False
        self._active_trace_id: Optional[str] = None
        self._current_journal: List[dict] = []
        self._journal_capacity: int = 1000  # Default (Phase 55)
        self._evolved_schema: Set[str] = set()

        # Idempotent close guard
        self._closed: bool = False
        self._subscribed_to_dispatcher: bool = False

        # Substrate Branching (Phase 39)
        self._parent_node_id: Optional[str] = None
        self._branch_label: Optional[str] = None

        # Phase 71: Decentralized Field Waves
        from app.event_dispatcher import get_dispatcher
        from app.semantic_events import SemanticEventType

        self._dispatcher = get_dispatcher()
        self._dispatcher.subscribe(SemanticEventType.FIELD_WAVE, self._on_field_wave)
        self._subscribed_to_dispatcher = True

    def close(self) -> None:
        """Unsubscribe from dispatcher and clean up resources.

        Idempotent and safe to call multiple times:
        - Subsequent calls return immediately.
        - Unsubscribe failures are logged but never raised.
        """
        if getattr(self, "_closed", False):
            return
        self._closed = True
        from app.semantic_events import SemanticEventType

        if self._subscribed_to_dispatcher:
            try:
                self._dispatcher.unsubscribe(SemanticEventType.FIELD_WAVE, self._on_field_wave)
                self._subscribed_to_dispatcher = False
            except Exception as exc:
                logger.debug("Failed to unsubscribe from dispatcher in close(): %s", exc)

    # ─── Public Getters & Identifiers ─────────────────────────────────────

    @property
    def node_id(self) -> str:
        return self._node_id

    @node_id.setter
    def node_id(self, value: str):
        self._node_id = value
        if hasattr(self, "_vector_clock"):
            self._vector_clock.node_id = value

    @property
    def evolved_schema(self) -> List[str]:
        return list(self._evolved_schema)

    # ─── Public Delegation: History Operations ────────────────────────────

    def record_decision(self, entry: dict):
        self._history.record_decision(entry)

    def trim_decision_history(self, max_size: int = 1000, keep: int = 500):
        self._history.trim_decision_history(max_size, keep)

    def get_recent_decisions(self, n: int = 20) -> list:
        return self._history.get_recent_decisions(n)

    def update_recent_decision_metadata(self, recent_copy: list, coherence: float, threshold: float):
        self._history.update_recent_decision_metadata(recent_copy, coherence, threshold)

    def get_topology_view(self):
        return self._topology.get_view()

    def clear_active_regions(self):
        with self._lock:
            self._topology.clear_regions()

    def set_region_energy(self, region_id: int, energy: float):
        self._topology.set_region_energy(region_id, energy)

    def record_cohesion_merge_attempt(self, pair: tuple):
        self._topology.record_cohesion_merge_attempt(pair)

    def record_cohesion_merge_success(self, pair: tuple):
        self._topology.record_cohesion_merge_success(pair)

    def record_cohesion_split_attempt(self, pair: tuple):
        self._topology.record_cohesion_split_attempt(pair)

    def record_cohesion_split_success(self, pair: tuple):
        self._topology.record_cohesion_split_success(pair)

    # ─── Substrate Branching (Phase 39) ──────────────────────────────────

    def branch(self, label: str) -> "SemanticWorldState":
        """Create an isolated branch of the current semantic world (Phase 39)."""
        import uuid

        child_id = f"{self._node_id}-br-{str(uuid.uuid4())[:4]}"
        child = SemanticWorldState(node_id=child_id)

        # Clone state via serialization
        state_snapshot = self.to_dict()
        child.from_dict(state_snapshot)

        # RESTORE child specific identifiers
        child.node_id = child_id
        child._parent_node_id = self._node_id
        child._branch_label = label

        # Initialize child's vector clock as a descendant of parent
        child._vector_clock.update(self._vector_clock.get_clock())

        logger.info(f"SUBSTRATE BRANCHED: [{
                self.node_id}] -> [{child_id}] (Label: {label})")
        return child

    # ─── Transaction Manager (MVCC & Thread Safety) ──────────────────────

    @contextmanager
    def transaction(self, label: str = "anonymous", trace_id: Optional[str] = None):
        """Context manager for atomic state transactions. Supports true concurrency with MVCC."""

        # 1. Nested Transaction Check
        if active_transaction.get() is not None:
            yield self
            return

        from app.failure_injector import get_injector

        injector = get_injector()

        states = [
            self._topology,
            self._energy,
            self._instability,
            self._manifold,
            self._motif,
            self._transition,
            self._intent,
            self._action,
            self._abstraction,
            self._observability,
            self._history,
        ]

        import uuid

        tx_ctx: Dict[str, Any] = {
            "label": label,
            "trace_id": trace_id or str(uuid.uuid4())[:8],
            "base_versions": {},
            "journal": [],
        }
        token = active_transaction.set(tx_ctx)

        try:
            start_time = time.time()
            for s in states:
                if hasattr(s, "begin_transaction"):
                    s.begin_transaction()
            yield self

            # 2. Commit Phase (Requires Global Lock)
            with self._lock:
                injector.inject(f"pre_commit:{label}")

                # Increment vector clock on commit
                self._vector_clock.increment()

                # Perform MVCC Validation
                expected_versions: Dict[str, int] = tx_ctx["base_versions"]
                val_start = time.time()

                from app.topology_state import ConflictError, TopologyState

                try:
                    for s in states:
                        if hasattr(s, "commit"):
                            injector.inject(f"mid_commit:{label}")
                            if isinstance(s, TopologyState):
                                s.commit(expected_versions=expected_versions)
                            else:
                                s.commit()
                except ConflictError as ce:
                    self.emit_telemetry(
                        "transaction_conflict",
                        {
                            "label": label,
                            "trace_id": tx_ctx["trace_id"],
                            "error": str(ce),
                            "regions_touched": len(expected_versions),
                        },
                    )
                    raise

                val_end = time.time()
                self.last_update_time = val_end

                # Record transaction in global journal
                tx = {
                    "label": label,
                    "timestamp": self.last_update_time,
                    "duration": self.last_update_time - start_time,
                    "validation_time_ms": (val_end - val_start) * 1000,
                    "clock": self._vector_clock.get_clock(),
                    "node_id": self.node_id,
                    "trace_id": tx_ctx["trace_id"],
                    "entries": list(tx_ctx["journal"]),
                }
                self._history.record_transaction(tx, capacity=self._journal_capacity)

                # Emit enhanced telemetry for the transaction itself
                self.emit_telemetry(
                    "transaction",
                    {
                        "label": label,
                        "duration": tx["duration"],
                        "validation_ms": tx["validation_time_ms"],
                        "entry_count": len(tx["entries"]) if isinstance(tx["entries"], list) else 0,
                        "regions_touched": len(expected_versions),
                        "trace_id": tx["trace_id"],
                        "node_id": self.node_id,
                    },
                )

        except Exception as e:
            # Best-effort rollback: if one subsystem fails to rollback,
            # log it and continue rolling back the others. Preserve the
            # original exception and re-raise it.
            rollback_errors: list[str] = []
            for s in states:
                if hasattr(s, "rollback"):
                    try:
                        s.rollback()
                    except Exception as rb_err:
                        rb_msg = f"{type(s).__name__}.rollback(): {rb_err}"
                        rollback_errors.append(rb_msg)
                        logger.error(
                            "Rollback failed for subsystem %s during transaction [%s]: %s",
                            type(s).__name__,
                            label,
                            rb_err,
                        )
            if rollback_errors:
                logger.error(
                    "State transaction [%s] rollback had %d subsystem error(s): %s",
                    label,
                    len(rollback_errors),
                    "; ".join(rollback_errors),
                )
            logger.error(
                "State transaction [%s] failed on node [%s] (Trace: %s), rolled back: %s",
                label,
                self.node_id,
                tx_ctx["trace_id"],
                e,
            )
            raise
        finally:
            active_transaction.reset(token)

    def replay_transaction(self, tx: dict):
        """Replay a transaction by executing its recorded entries."""
        label = tx.get("label", "replayed")
        self._replaying = True
        try:
            with self.transaction(f"replay:{label}"):
                for entry in tx.get("entries", []):
                    subsystem = entry.get("subsystem")
                    action = entry.get("action")
                    details = entry.get("details", {})

                    target: Any = None
                    if subsystem == "topology":
                        target = self._topology
                    elif subsystem == "energy":
                        target = self._energy
                    elif subsystem == "instability":
                        target = self._instability
                    elif subsystem == "manifold":
                        target = self._manifold
                    elif subsystem == "motif":
                        target = self._motif
                    elif subsystem == "transition":
                        target = self._transition
                    elif subsystem == "intent":
                        target = self._intent
                    elif subsystem == "action":
                        target = self._action
                    elif subsystem == "abstraction":
                        target = self._abstraction
                    elif subsystem == "observability":
                        target = self._observability
                    elif subsystem == "history":
                        target = self._history
                    elif subsystem == "global":
                        continue

                    if target and hasattr(target, action):
                        method = getattr(target, action)
                        try:
                            details = dict(details)
                            if subsystem == "instability" and "key" in details:
                                details["key"] = tuple(details["key"])
                            if subsystem == "manifold" and "key" in details:
                                details["key"] = tuple(details["key"])
                            if subsystem == "observability" and action == "emit_telemetry":
                                details["event_type"] = details.pop("type", None)
                            details = self._filter_replay_details(method, details)
                            method(**details)
                        except Exception as e:
                            logger.warning(f"Replay failed for {subsystem}.{action}: {e}")
        finally:
            self._replaying = False

    def _filter_replay_details(self, method: Any, details: dict) -> dict:
        import inspect

        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):
            return details

        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
            return details

        allowed = {
            name
            for name, param in signature.parameters.items()
            if param.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        return {key: value for key, value in details.items() if key in allowed}

    def record_delta(self, subsystem: str, action: str, details: dict):
        """Record a state delta in the current transaction journal."""
        if self._replaying:
            return

        tx = active_transaction.get()
        entry = {
            "subsystem": subsystem,
            "action": action,
            "details": deepcopy(details),
            "timestamp": time.time(),
            "trace_id": tx["trace_id"] if tx else None,
        }

        # Push to global EventJournal
        from app.event_journal import get_journal

        get_journal().record(
            source=subsystem, mutation_type=action, before={}, after=details, metadata={"trace_id": entry["trace_id"]}
        )

        if tx is not None:
            tx["journal"].append(entry)
        else:
            with self._lock:
                direct_tx = {
                    "label": "direct_mutation",
                    "timestamp": entry["timestamp"],
                    "duration": 0,
                    "clock": self._vector_clock.get_clock(),
                    "node_id": self.node_id,
                    "entries": [entry],
                    "trace_id": entry["trace_id"],
                }
                self._history.record_transaction(direct_tx, capacity=self._journal_capacity)

    def record_read(self, region_id: str, version: int):
        tx = active_transaction.get()
        if tx is not None:
            tx["base_versions"][region_id] = version

    def trace_causality(self, limit: int = 100) -> List[dict]:
        history_journal = self._history.transaction_journal
        return history_journal[-limit:] if history_journal else []

    # ─── Distributed Consensus (Phase 32) ───────────────────────────────

    def merge_state(self, remote_data: dict, trace_id: Optional[str] = None):
        """Merge a remote world state into the local state using vector clocks (Phase 32)."""
        remote_node = remote_data.get("node_id")
        remote_clock = remote_data.get("clock", {})
        active_trace = trace_id or remote_data.get("last_trace_id")

        relation = self._vector_clock.compare(remote_clock)
        if relation in ("ancestor", "equal"):
            logger.info(f"CONSENSUS: Ignoring remote state from [{remote_node}] (Ancestor / Equal)")
            return

        alpha = 0.7 if relation == "descendant" else 0.3

        with self.transaction(f"merge:{remote_node}", trace_id=active_trace):
            self._vector_clock.update(remote_clock)
            self._energy.merge(remote_data, alpha=alpha)
            self._manifold.merge(remote_data, alpha=alpha)
            self._instability.merge(remote_data)
            self._topology.merge(remote_data.get("topology", {}), alpha=alpha)

            remote_history = remote_data.get("history", {})
            self._history.merge_journal(remote_history.get("transaction_journal", []))

            remote_schema = set(remote_data.get("evolved_schema", []))
            self._evolved_schema.update(remote_schema)

            logger.info(
                f"CONSENSUS: Merged state from [{remote_node}]. Relation: {relation}, Alpha: {alpha} (Trace: {active_trace})"
            )
            self.record_delta(
                "global",
                "merge_state",
                {
                    "remote_node": remote_node,
                    "relation": relation,
                    "alpha": alpha,
                    "remote_trace": remote_data.get("last_trace_id"),
                },
            )

    # ─── Manifold Federation ─────────────────────────────────────────────

    def export_manifold(self) -> dict:
        """Export learned role embeddings with Differential Noise (Phase 30)."""
        import random

        manifold = self.role_manifold

        for role in manifold:
            vec = manifold[role]
            noise = [random.gauss(0, 0.01) for _ in range(16)]
            for i in range(16):
                vec[i] = max(0.0, min(1.0, vec[i] + noise[i]))
            manifold[role] = vec

        return {
            "manifold": manifold,
            "version": "1.1",
            "timestamp": time.time(),
            "origin": id(self),
            "privacy": "differential_noise_v1",
        }

    def import_federated_manifold(self, data: dict):
        """Merge federated role embeddings into local manifold with Ontological Firewall (Phase 30)."""
        remote_manifold = data.get("manifold", {})
        with self.transaction("manifold_federation"):
            filtered_count = 0
            for role, remote_vec in remote_manifold.items():
                entropy = sum(1.0 - abs(v - 0.5) * 2.0 for v in remote_vec) / 16.0
                if entropy > 0.9:
                    filtered_count += 1
                    continue

                if self._manifold.has_manifold_role(role):
                    if self._manifold.is_role_anchored(role):
                        filtered_count += 1
                        continue

                    local_vec = self._manifold.get_manifold_vector(role)
                    dist = sum((a - b) ** 2 for a, b in zip(local_vec, remote_vec)) ** 0.5
                    if dist > 1.5:
                        filtered_count += 1
                        continue

                    self._manifold.blend_manifold_vector(role, remote_vec, alpha=0.8, beta=0.2)
                else:
                    self._manifold.set_manifold_vector(role, remote_vec)
                    self._energy.set_schema_instability(role, 0.3)

            logger.info(f"FEDERATION: Merged {
                    len(remote_manifold) -
                    filtered_count} roles. " f"Firewall filtered {filtered_count} roles.")
            self.record_delta(
                "global", "manifold_federation", {"remote_roles": len(remote_manifold), "filtered": filtered_count}
            )

    def export_topology_laws(self) -> dict:
        return {
            "laws": {f"{k[0]}|{k[1]}": v for k, v in self._topology.topological_laws.items()},
            "version": "1.0",
            "timestamp": time.time(),
        }

    def import_federated_laws(self, data: dict):
        remote_laws = data.get("laws", {})
        with self.transaction("federated_laws"):
            for key_str, remote_val in remote_laws.items():
                parts = key_str.split("|")
                if len(parts) == 2:
                    pair = tuple(parts)
                    local_val = self._topology.topological_laws.get(pair, 0.0)
                    new_val = local_val * 0.7 + remote_val * 0.3
                    self._topology.set_topological_law(pair, new_val)

            logger.info(f"FEDERATION: Merged {
                    len(remote_laws)} topological laws.")
            self.record_delta("global", "federated_laws", {"remote_laws": len(remote_laws)})

    # ─── Cognitive Health Summary ────────────────────────────────────────

    def get_cognitive_health(self) -> dict:
        from app.semantic_inference_engine import RoleEmbeddingEngine

        reng = RoleEmbeddingEngine()

        certainty = reng.get_certainty()
        roles = self._manifold.get_manifold_roles()
        active_roles = [r for r in roles if not r.startswith("hypo_")]
        hypo_roles = [r for r in roles if r.startswith("hypo_")]

        communities = self.global_communities
        fragmentation = len(communities) / max(len(active_roles), 1)

        from app.semantic_allocation_engine import _infer_role_type

        alignment_total = 0.0
        for role in active_roles:
            seed_type = _infer_role_type(role)
            seed_vec = reng._get_type_vector(seed_type)
            role_vec = self._manifold.get_manifold_vector(role)
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
                "anchored": len(self._manifold.role_anchors),
            },
            "system_energy": round(self.metrics.global_energy, 3),
            "stability_debt": round(self.metrics.stability_debt, 3),
        }

    # ─── Manifold Delegation Methods ──────────────────────────────────────

    def set_manifold_vector(self, role: str, vector: list):
        self._manifold.set_manifold_vector(role, vector)

    def get_manifold_vector(self, role: str) -> list:
        return self._manifold.get_manifold_vector(role)

    def has_manifold_role(self, role: str) -> bool:
        return self._manifold.has_manifold_role(role)

    def get_manifold_roles(self) -> list:
        return self._manifold.get_manifold_roles()

    def is_role_anchored(self, role: str) -> bool:
        return self._manifold.is_role_anchored(role)

    def remove_manifold_role(self, role: str):
        self._manifold.remove_manifold_role(role)

    def blend_manifold_vector(self, role: str, other_vector: list, alpha: float = 0.7, beta: float = 0.3):
        self._manifold.blend_manifold_vector(role, other_vector, alpha, beta)

    def get_manifold_checksum(self) -> str:
        return self._manifold.get_manifold_checksum()

    def clear_compatibility(self):
        self._manifold.clear_compatibility()

    def clear_compatibility_for_key(self, key: tuple):
        self._manifold.clear_compatibility_for_key(key)

    def set_compatibility(self, role: str, type_str: str, value: float):
        self._manifold.set_compatibility(role, type_str, value)

    def get_compatibility(self, role: str, type_str: str) -> float:
        return self._manifold.get_compatibility(role, type_str)

    def expand_dimensions(self, new_dim: int):
        self._manifold.expand_dimensions(new_dim)

    def get_shards(self) -> set:
        return self._manifold.get_shards()

    def get_shard_roles(self, shard_id: str) -> list:
        return self._manifold.get_shard_roles(shard_id)

    def shard_substrate(self) -> Dict[str, List[str]]:
        self._topology.detect_communities()
        self._manifold.shard_manifold(self._topology.global_communities)
        return self._topology.shard_topology()

    def apply_force_to_manifold(self, role: str, deltas: list, clamp: bool = True):
        self._manifold.apply_force_to_manifold(role, deltas, clamp)

    def anchor_role(self, role: str):
        self._manifold.anchor_role(role)

    def increment_co_occurrence(self, key: tuple, delta: int = 1):
        self._manifold.increment_co_occurrence(key, delta)

    @property
    def manifold_dimension(self) -> int:
        return self._manifold.dimension

    @property
    def role_anchors(self) -> set:
        return self._manifold.role_anchors

    # ─── Abstraction Delegation Methods ───────────────────────────────────

    def get_role_level(self, role: str) -> int:
        return self._abstraction.get_role_level(role)

    def get_envelope(self, envelope_id: str) -> Optional[dict]:
        return self._abstraction.get_envelope(envelope_id)

    @property
    def abstraction_envelopes(self) -> dict:
        return self._abstraction.envelopes

    # ─── Observability Delegation Methods ────────────────────────────────

    def emit_telemetry(self, event_type: str, details: dict):
        self._observability.emit_telemetry(event_type, details, trace_id=self._active_trace_id)

    def record_degradation(
        self,
        subsystem: str,
        severity: str,
        cause: str,
        topology_state: Optional[str] = None,
        semantic_entropy: Optional[float] = None,
    ):
        self._observability.record_degradation(
            subsystem=subsystem,
            severity=severity,
            cause=cause,
            trace_id=self._active_trace_id,
            topology_state=topology_state,
            semantic_entropy=semantic_entropy,
        )

    @property
    def observability_telemetry(self) -> list:
        return self._observability.telemetry

    @property
    def observability_heatmap(self) -> dict:
        return self._observability.heatmap

    def get_role_drift(self, role: str) -> list:
        return self._observability.get_role_drift(role)

    def get_causal_telemetry(self) -> list:
        return self._observability.get_causal_telemetry()

    def log_drift(self, role: str, drift: float):
        self._observability.log_drift(role, drift)

    # ─── Intent Delegation Methods ───────────────────────────────────────

    def set_intent(self, intent_id: str, target_vec: list, strength: float = 0.5, target_roles: Optional[list] = None):
        self._intent.set_intent(intent_id, target_vec, strength, target_roles)

    def remove_intent(self, intent_id: str):
        self._intent.remove_intent(intent_id)

    def clear_intents(self):
        self._intent.clear()

    @property
    def active_intents(self) -> dict:
        return self._intent.active_intents

    # ─── Action Delegation Methods ───────────────────────────────────────

    def register_action(self, action_id: str, target_vec: list, handler_name: str, threshold: float = 0.3):
        self._action.register_action(action_id, target_vec, handler_name, threshold)

    def log_action_execution(self, action_id: str, success: bool, details: Optional[dict] = None):
        self._action.log_execution(action_id, success, details)

    def get_action(self, action_id: str) -> Optional[dict]:
        return self._action.get_action(action_id)

    @property
    def active_actions(self) -> dict:
        return self._action.active_actions

    @property
    def action_history(self) -> list:
        return self._action.action_history

    # ─── Transition Delegation Methods ───────────────────────────────────

    def update_seed_transition(self, data: dict):
        self._transition.update_seed(data)

    def get_transition_prob(self, type_a: str, type_b: str) -> float:
        return self._transition.get_prob(type_a, type_b)

    def observe_transition(self, type_a: str, type_b: str, is_role_boundary: bool):
        self._transition.observe(type_a, type_b, is_role_boundary)

    def get_high_transition_types(self, threshold: float = 0.6) -> list:
        return self._transition.get_high_transition_types(threshold)

    # ─── Vector Clock Delegation ─────────────────────────────────────────

    def get_vector_clock(self) -> dict:
        return self._vector_clock.to_dict()

    # ─── Instability Delegation Methods ──────────────────────────────────

    def get_exclusion(self, r1: str, r2: str) -> float:
        return self._instability.get_exclusion(r1, r2)

    def set_exclusion_by_key(self, key: tuple, value: float):
        self._instability.set_exclusion(key, value)
        if value > 0.3:
            current_law = self._topology.topological_laws.get(key, 0.0)
            new_law = current_law - value * 0.05
            self._topology.set_topological_law(key, new_law)

    # ─── Energy Delegation Methods ────────────────────────────────────────

    def accumulate_density(self, delta: float):
        self._energy.accumulate_density(delta)

    def increment_records(self, n: int = 1):
        self._energy.increment_records(n)

    # ─── Energy & Topology API Delegation Properties ───────────────────────

    @property
    def energy_state(self):
        return self._energy

    @property
    def topology_state(self):
        return self._topology

    @property
    def topology_anchors(self) -> set:
        return self._topology.anchors

    @property
    def meso_clusters(self) -> list:
        return self._topology.meso_clusters

    def compute_meso_clusters(self):
        self._topology.compute_meso_clusters()

    def compute_macro_from_meso(self) -> dict:
        return self._topology.compute_macro_from_meso()

    @property
    def macro_continents(self) -> list:
        return self._topology.get_view().get_macro_continents()

    def compute_macro_continents(self):
        self._topology.compute_macro_continents()

    # ─── Authority Delegation Properties ─────────────────────────────────

    @property
    def field_regions(self):
        return self._topology.get_view().all_regions()

    @field_regions.setter
    def field_regions(self, value):
        self._topology.replace_all(list(value))

    @property
    def learned_exclusions(self):
        return dict(self._instability.exclusions)

    # ─── Delegation Properties: ManifoldState ─────────────────────────────

    @property
    def role_manifold(self):
        return {k: list(v) for k, v in self._manifold.role_manifold.items()}

    @property
    def role_compatibility(self):
        return dict(self._manifold.role_compatibility)

    @property
    def role_position_memory(self):
        return {k: list(v) for k, v in self._manifold.role_position_memory.items()}

    @role_position_memory.setter
    def role_position_memory(self, value):
        self._manifold.role_position_memory = value

    @property
    def role_co_occurrence(self):
        return dict(self._manifold.role_co_occurrence)

    @property
    def learning_count(self) -> int:
        return self._manifold.learning_count

    @learning_count.setter
    def learning_count(self, value: int):
        self._manifold.set_learning_count(value)

    @property
    def total_co_occurrences(self) -> int:
        return self._manifold.total_co_occurrences

    @total_co_occurrences.setter
    def total_co_occurrences(self, value: int):
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
    def transition_observations(self) -> int:
        return self._transition.transition_observations

    @transition_observations.setter
    def transition_observations(self, value: int):
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
    def field_activation_count(self) -> int:
        return self._history.field_activation_count

    @field_activation_count.setter
    def field_activation_count(self, value: int):
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

    # ─── Dynamic Abstraction & Agency ─────────────────────────────────────

    def dispatch_actions(self) -> int:
        triggered = 0
        active_actions = self._action.active_actions
        if not active_actions:
            return 0

        from app.llm_bridge import get_plugin_manager
        from app.policy_engine import get_policy_engine

        policy = get_policy_engine(ws=self)
        plugins = get_plugin_manager(ws=self)
        pressure = self.get_system_pressure()

        with self.transaction("action_dispatch"):
            for region in self._topology.iterate_regions():
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

                            dist = sum((a - b) ** 2 for a, b in zip(role_vec, target_vec)) ** 0.5

                            if dist < threshold:
                                logger.info(f"AGENCY TRIGGERED: Role [{role}] activated Action [{aid}] (Dist: {
                                        dist:.4f})")

                                success = True
                                tool_result = None
                                try:
                                    tool_result = plugins.call_tool(handler_name, role=role, token=region.token)
                                except Exception as e:
                                    logger.warning(f"Plugin execution failed for {handler_name}: {e}")
                                    success = False

                                self._action.log_execution(
                                    aid,
                                    success=success,
                                    details={
                                        "role": role,
                                        "token": region.token,
                                        "distance": dist,
                                        "tool_result": str(tool_result)[:100] if tool_result else None,
                                    },
                                )
                                triggered += 1
                                if success:
                                    self._manifold.blend_manifold_vector(role, target_vec, alpha=0.95, beta=0.05)

            if triggered > 0:
                self.record_delta("global", "dispatch_actions", {"count": triggered})

        return triggered

    def synthesize_hierarchical_envelopes(self):
        communities = self._topology.global_communities
        if not communities:
            return

        with self.transaction("hierarchical_synthesis"):
            for idx, community in enumerate(communities):
                if len(community) < 2:
                    continue

                total_instability = 0.0
                for role in community:
                    total_instability += self.metrics.schema_instability.get(role, 0.5)
                n_comm = len(community)
                avg_instability = total_instability / n_comm if n_comm > 0 else 1.0

                if avg_instability < 0.2:
                    envelope_id = f"env_{idx}_{int(time.time())}"

                    constituents = list(community)
                    vectors = [self._manifold.get_manifold_vector(r) for r in constituents]
                    vectors = [v for v in vectors if v]
                    if not vectors:
                        continue

                    n_vectors = len(vectors)
                    dim = len(vectors[0])
                    centroid = [0.0] * dim
                    for v in vectors:
                        for k in range(dim):
                            centroid[k] += v[k]
                    centroid = [c / n_vectors for c in centroid]

                    self._abstraction.create_envelope(envelope_id, constituents, centroid, level=1)
                    self._manifold.set_manifold_vector(envelope_id, centroid)
                    self._manifold.anchor_role(envelope_id)

                    logger.info(
                        f"HIERARCHICAL SYNTHESIS: Distilled community {constituents} into Envelope [{envelope_id}]"
                    )

    def merge_hierarchical_knowledge(self, other_abstraction: dict):
        remote_envelopes = other_abstraction.get("envelopes", {})
        if not remote_envelopes:
            return

        with self.transaction("hierarchical_merge"):
            local_envelopes = self._abstraction.envelopes

            for rid, r_details in remote_envelopes.items():
                r_vec = r_details["manifold_vec"]

                merged = False
                for lid, l_details in local_envelopes.items():
                    l_vec = l_details["manifold_vec"]
                    dist = sum((a - b) ** 2 for a, b in zip(l_vec, r_vec)) ** 0.5

                    if dist < 0.15:
                        new_constituents = set(l_details["constituents"]) | set(r_details["constituents"])
                        new_vec = [(a + b) / 2 for a, b in zip(l_vec, r_vec)]

                        self._abstraction.create_envelope(
                            lid, list(new_constituents), new_vec, level=max(l_details["level"], r_details["level"])
                        )
                        self._manifold.set_manifold_vector(lid, new_vec)

                        logger.info(f"HIERARCHICAL MERGE: Merged remote concept {rid} into local [{lid}] (Dist: {
                                dist:.4f})")
                        merged = True
                        break

                if not merged:
                    self._abstraction.create_envelope(rid, r_details["constituents"], r_vec, level=r_details["level"])
                    self._manifold.set_manifold_vector(rid, r_vec)
                    self._manifold.anchor_role(rid)

    # ─── Operations & Search Queries ──────────────────────────────────────

    def topological_search(self, query: str) -> list:
        return self._history.topological_search(query)

    def execute_tql(self, query: str) -> dict:
        from app.topological_query import get_tql_engine

        return get_tql_engine(ws=self).execute_tql(query)

    def get_crystalline_attractors(self, token_vals=None) -> list:
        return self._history.get_crystalline_attractors(token_vals)

    @requires_invariants
    def _synthesize_crystalline_record(self, record: dict, current_record: Optional[int] = None):
        idx = current_record if current_record is not None else self.metrics.total_records_processed
        self._history.synthesize_crystalline(record, idx)

    @requires_invariants
    def aggregate_from_regions(self):
        if self._topology.region_count() == 0:
            self._energy.set_convergence(self._energy.convergence)
            return
        self._energy.update_from_regions(list(self._topology.iterate_regions()))

    @requires_invariants
    def decay_field_regions(self):
        self.evolve_field()

    def snapshot(self, label: str = ""):
        self._history.add_snapshot(
            {
                "label": label,
                "time": self.metrics.total_records_processed,
                "energy": self.metrics.global_energy,
                "uncertainty": self.metrics.average_uncertainty,
                "field_pressure": self.metrics.field_pressure,
                "exclusions": len(self.learned_exclusions),
                "compatibilities": len(self.role_compatibility),
                "motifs": len(self.motif_counts),
            }
        )
        self._history.trim_snapshots(max_size=500, keep=250)

    def replay(self) -> list:
        return self._history.get_snapshots()

    def trace_waves(self) -> list:
        return self._history.get_wave_snapshots()

    def diff_snapshots(self, idx_a: int = -2, idx_b: int = -1) -> dict:
        return self._history.diff_snapshots(idx_a, idx_b)

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
        self._scheduler.clear()
        self.last_update_time = time.time()

    def schedule_cognitive_task(self, task_id: str, priority: Any, handler: Callable, *args, **kwargs):
        self._scheduler.schedule(task_id, priority, handler, *args, **kwargs)

    def process_cognitive_queue(self, budget_ms: float = 100.0) -> int:
        return self._scheduler.step(budget_ms=budget_ms)

    # ─── Divergence & Merge (Phase 39) ───────────────────────────────────

    def mutation_diff(self, other: "SemanticWorldState") -> dict:
        diff: dict = {}
        if self.metrics.total_records_processed != other.metrics.total_records_processed:
            diff["records_processed"] = (self.metrics.total_records_processed, other.metrics.total_records_processed)
        if self.metrics.global_energy != other.metrics.global_energy:
            diff["global_energy"] = (self.metrics.global_energy, other.metrics.global_energy)
        if self.metrics.global_entropy != other.metrics.global_entropy:
            diff["global_entropy"] = (self.metrics.global_entropy, other.metrics.global_entropy)
        added_roles = set(other.role_compatibility) - set(self.role_compatibility)
        if added_roles:
            diff["added_role_compatibilities"] = {
                str(k): v for k, v in other.role_compatibility.items() if k in added_roles
            }
        changed_roles = {
            k
            for k in set(self.role_compatibility) & set(other.role_compatibility)
            if abs(self.role_compatibility[k] - other.role_compatibility[k]) > 0.01
        }
        if changed_roles:
            diff["changed_role_compatibilities"] = {
                str(k): (self.role_compatibility[k], other.role_compatibility[k]) for k in changed_roles
            }
        added_motifs = set(other.motif_counts) - set(self.motif_counts)
        if added_motifs:
            diff["added_motifs"] = [str(m) for m in added_motifs]
        new_exclusions = set(other.learned_exclusions) - set(self.learned_exclusions)
        if new_exclusions:
            diff["new_exclusions"] = [str(e) for e in new_exclusions]
        return diff

    def semantic_diff(self, other: "SemanticWorldState") -> dict:
        divergence = {
            "manifold_drift": 0.0,
            "new_roles": [],
            "missing_roles": [],
            "tension_delta": 0.0,
        }

        local_m = self._manifold.role_manifold
        other_m = other._manifold.role_manifold

        common_roles = set(local_m.keys()) & set(other_m.keys())
        if common_roles:
            n_common = len(common_roles)
            total_dist = 0.0
            for r in common_roles:
                v1, v2 = local_m[r], other_m[r]
                dist = sum((a - b) ** 2 for a, b in zip(v1, v2)) ** 0.5
                total_dist += dist
            divergence["manifold_drift"] = total_dist / n_common if n_common > 0 else 0.0

        divergence["new_roles"] = list(set(other_m.keys()) - set(local_m.keys()))
        divergence["missing_roles"] = list(set(local_m.keys()) - set(other_m.keys()))
        divergence["tension_delta"] = abs(other.metrics.global_energy - self.metrics.global_energy)

        return divergence

    def merge_branch(self, branch: "SemanticWorldState", alpha: float = 0.5):
        """Merge an isolated branch back into the current state (Phase 39)."""
        with self.transaction(f"merge_branch:{branch.node_id}"):
            self._manifold.merge(branch._manifold.to_dict(), alpha=alpha)
            self._instability.merge(branch._instability.to_dict())
            self._motif.merge(branch._motif.to_dict())
            self.merge_hierarchical_knowledge(branch._abstraction.to_dict())
            self._vector_clock.update(branch._vector_clock.get_clock())

            logger.info(f"SUBSTRATE MERGED: [{branch.node_id}] -> [{self.node_id}] (Alpha: {alpha})")
