"""Federation Manager — operational governance for sharded multi-node state synchronization.

Provides:
  - Stable node registration and sharding workload boundaries.
  - Multi-node conflict-resolution rules (LWW for reputation, Union for motifs).
  - Transaction replay validation to prevent partition and drift split-brains.
  - Divergence and network partition simulation monitoring.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

_REPLAY_LOCK = threading.Lock()

logger = logging.getLogger(__name__)


def _encode_motif_fields(fields: list[str]) -> str:
    """Encode motif fields without depending on field-name delimiters."""
    return json.dumps(sorted(fields), separators=(",", ":"))


def _decode_motif_key(key: str) -> list[str]:
    """Decode a motif key, preserving support for the legacy dash format."""
    try:
        decoded = json.loads(key)
    except json.JSONDecodeError:
        return key.split("-")
    if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
        return decoded
    return key.split("-")


def _schema_contains_motif(schema: set[str], motif_fields: list[str]) -> bool:
    expected = sorted(motif_fields)
    return any(sorted(_decode_motif_key(existing)) == expected for existing in schema)


@dataclass
class ShardStateSnapshot:
    """Standardized snapshot format for remote sharded state transfers."""

    node_id: str
    shard_id: str
    timestamp: float
    transaction_id: int
    # Domain reputations: domain -> {consecutive_failures, total_fetches,
    # cooldown_until, last_update}
    domain_reputation: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Learned motifs: list of field co-occurrence lists
    motifs: list[list[str]] = field(default_factory=list)
    # Topological state: "src:tgt" -> cohesion mapping
    topology: dict[str, float] = field(default_factory=dict)
    # Topological metadata: "src:tgt" -> {node_id, timestamp, version, epoch}
    topology_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Transactional delta log for replay checks
    delta_log: list[dict[str, Any]] = field(default_factory=list)


class FederationManager:
    """Manages multi-node consensus, merge rules, and transactional rejoin reconciliations."""

    def __init__(self, world_state: Any) -> None:
        self.ws = world_state
        from app.config import settings

        self.node_id = settings.NODE_ID
        self.shard_id = settings.SHARD_ID
        self._metrics_lock = threading.Lock()
        self.registered_nodes: dict[str, dict[str, Any]] = {}
        self.last_sync_timestamps: dict[str, float] = {}
        self.divergence_metrics: dict[str, Any] = {
            "reconciled_merges": 0,
            "drift_warnings": 0,
            "failed_replays": 0,
            "last_drift_score": 0.0,
        }

    def register_node(self, node_id: str, shard_id: str) -> None:
        """Register a remote node context under federation control."""
        if node_id == self.node_id:
            return

        if len(self.registered_nodes) >= 1000 and node_id not in self.registered_nodes:
            # Evict the oldest seen node to prevent memory exhaustion
            oldest = min(self.registered_nodes.keys(), key=lambda k: self.registered_nodes[k].get("last_seen", 0))
            self.registered_nodes.pop(oldest, None)

        self.registered_nodes[node_id] = {
            "shard_id": shard_id,
            "last_seen": time.time(),
            "status": "active",
        }
        logger.info("[Federation] Registered remote node %s on shard %s", node_id, shard_id)

    def export_local_state(self) -> ShardStateSnapshot:
        """Export local world state, including domain reputations and transaction deltas."""
        # 1. Gather domain reputations from crawl policy engine
        from app.crawl_policy import get_crawl_policy

        policy = get_crawl_policy()
        domain_states = {}
        for domain, state in policy.iter_domain_states():
            domain_states[domain] = {
                "consecutive_failures": state.consecutive_failures,
                "total_fetches": state.total_fetches,
                "cooldown_until": state.cooldown_until,
                "last_update": state.last_fetch_time,
            }

        # 2. Gather learned motifs from world state.
        motifs = [_decode_motif_key(m) for m in self.ws.evolved_schema]

        # 3. Gather local topology coordinates from world state (serialize
        # tuple keys) — use public cohesion accessor
        exported_cohesion = self.ws.export_cohesion_state()
        topology_coords = {k: v["cohesion"] for k, v in exported_cohesion.items()}
        topology_metadata = {k: v["metadata"] for k, v in exported_cohesion.items()}

        # 4. Gather local transaction journals / deltas
        delta_log = getattr(self.ws, "_current_journal", [])

        # Fetch latest transaction depth / counter
        tx_id = getattr(self.ws, "_transaction_depth", 0)

        return ShardStateSnapshot(
            node_id=self.node_id,
            shard_id=self.shard_id,
            timestamp=time.time(),
            transaction_id=tx_id,
            domain_reputation=domain_states,
            motifs=motifs,
            topology=topology_coords,
            topology_metadata=topology_metadata,
            delta_log=delta_log,
        )

    def merge_remote_state(self, remote: ShardStateSnapshot) -> dict[str, Any]:
        """Merge remote state snapshot into the local world state using absolute laws."""
        self.register_node(remote.node_id, remote.shard_id)
        self.last_sync_timestamps[remote.node_id] = remote.timestamp

        merge_report = {
            "merged_domains": 0,
            "merged_motifs": 0,
            "reconciled_topologies": 0,
            "replayed_transactions": 0,
        }

        # Serialize the entire merge so overlapping gossip/merge cycles
        # cannot race on shared world state mutations (self.ws.*).
        with self._metrics_lock:
            # Rule 1: LWW (Last-Write-Wins) for Domain Reputation State
            from app.crawl_policy import get_crawl_policy

            policy = get_crawl_policy()
            for domain, rep in remote.domain_reputation.items():
                local_state = policy.get_or_create_domain_state(domain)
                remote_timestamp = rep.get("last_update", 0.0)

                # Only merge if remote was updated more recently
                if remote_timestamp > local_state.last_fetch_time:
                    local_state.consecutive_failures = rep["consecutive_failures"]
                    local_state.total_fetches = rep["total_fetches"]
                    local_state.cooldown_until = rep["cooldown_until"]
                    local_state.last_fetch_time = remote_timestamp
                    merge_report["merged_domains"] += 1

            # Rule 2: Structural Union for Learned Motifs
            for motif_fields in remote.motifs:
                motif_hash = _encode_motif_fields(motif_fields)
                evolved = set(self.ws.evolved_schema)
                if not _schema_contains_motif(evolved, motif_fields):
                    self.ws._evolved_schema.add(motif_hash)
                    merge_report["merged_motifs"] += 1

            # Rule 3: Topological Affinity Merging via Deterministic Epoch &
            # Version Consensus  — uses public cohesion export/import API
            local_cohesion_state = self.ws.export_cohesion_state()
            remote_meta_dict = getattr(remote, "topology_metadata", {})

            for key, remote_cohesion in remote.topology.items():
                parts = key.split(":")
                if len(parts) != 2:
                    continue

                # 1. Fetch remote version metadata, or default to standard LWW
                r_meta = remote_meta_dict.get(
                    key,
                    {"node_id": remote.node_id, "timestamp": remote.timestamp, "version": 1, "epoch": 0},
                )
                r_epoch = r_meta.get("epoch", 0)
                r_ver = r_meta.get("version", 1)
                r_ts = r_meta.get("timestamp", remote.timestamp)
                r_node = r_meta.get("node_id", remote.node_id)

                # 2. Fetch local version metadata from exported state
                local_entry = local_cohesion_state.get(key)
                l_meta = (
                    local_entry["metadata"]
                    if local_entry
                    else {
                        "node_id": self.node_id,
                        "timestamp": 0.0,
                        "version": 0,
                        "epoch": 0,
                    }
                )
                l_epoch = l_meta.get("epoch", 0)
                l_ver = l_meta.get("version", 0)
                l_ts = l_meta.get("timestamp", 0.0)
                l_node = l_meta.get("node_id", self.node_id)

                # If remote metadata was not explicitly provided, fall back
                # to cooperative averaging
                if not remote_meta_dict or key not in remote_meta_dict:
                    if local_entry:
                        averaged = (local_entry["cohesion"] + remote_cohesion) / 2.0
                        self.ws.import_cohesion_entry(
                            key,
                            averaged,
                            {
                                "node_id": self.node_id,
                                "timestamp": time.time(),
                                "version": (l_ver if isinstance(l_ver, int) else 0) + 1,
                                "epoch": l_epoch,
                            },
                        )
                    else:
                        self.ws.import_cohesion_entry(
                            key,
                            remote_cohesion,
                            {
                                "node_id": self.node_id,
                                "timestamp": time.time(),
                                "version": 1,
                                "epoch": l_epoch,
                            },
                        )
                    merge_report["reconciled_topologies"] += 1
                    continue

                # 3. Apply Deterministic Multi-Shard Consensus Policies
                remote_wins = False
                if r_epoch > l_epoch or (
                    r_epoch == l_epoch
                    and (r_ver > l_ver or (r_ver == l_ver and (r_ts > l_ts or (r_ts == l_ts and r_node > l_node))))
                ):
                    remote_wins = True

                # 4. If remote wins, write remote cohesion and metadata
                # Otherwise, remote is discarded (local retains authority)
                if remote_wins or not local_entry:
                    self.ws.import_cohesion_entry(key, remote_cohesion, r_meta)
                    merge_report["reconciled_topologies"] += 1

            self.divergence_metrics["reconciled_merges"] += 1
        logger.info("[Federation] Successfully merged remote state from node %s: %s", remote.node_id, merge_report)
        return merge_report

    def replay_deltas(self, deltas: list[dict[str, Any]]) -> dict[str, Any]:
        """Sequence and replay remote state transactions to reconcile partition drifts."""
        replay_report = {
            "received": len(deltas),
            "replayed": 0,
            "failed": 0,
        }

        # Prevent replay storm if local world state is currently processing
        with _REPLAY_LOCK:
            if getattr(self.ws, "_replaying", False):
                return replay_report
            self.ws._replaying = True
        try:
            # Serialize world-state mutations alongside merge_remote_state.
            with self._metrics_lock:
                for delta in sorted(deltas, key=lambda d: d.get("timestamp", 0.0)):
                    try:
                        action = delta.get("action")
                        if action == "add_motif":
                            motif = delta.get("payload", {}).get("motif")
                            if motif:
                                self.ws._evolved_schema.add(motif)
                                replay_report["replayed"] += 1
                        elif action == "record_failure":
                            domain = delta.get("payload", {}).get("domain")
                            fail_type = delta.get("payload", {}).get("fail_type")
                            if domain and fail_type:
                                self.ws.regression.record_failure(domain, fail_type)
                                replay_report["replayed"] += 1
                    except Exception as e:
                        replay_report["failed"] += 1
                        self.divergence_metrics["failed_replays"] += 1
                        logger.warning("[Federation] Replay delta action failed: %s", e)
        finally:
            self.ws._replaying = False

        return replay_report

    def compute_drift_divergence(self, remote: ShardStateSnapshot) -> float:
        """Calculate topological drift and semantic distance divergence [0.0 - 1.0]."""
        exported = self.ws.export_cohesion_state()
        local_coords = {k: v["cohesion"] for k, v in exported.items()}

        if not local_coords or not remote.topology:
            return 0.0

        shared_keys = set(local_coords.keys()) & set(remote.topology.keys())
        if not shared_keys:
            return 1.0  # Complete divergence

        total_distance = sum(abs(local_coords[k] - remote.topology[k]) for k in shared_keys)
        avg_drift = total_distance / len(shared_keys)

        with self._metrics_lock:
            self.divergence_metrics["last_drift_score"] = round(avg_drift, 4)
        if avg_drift > 0.5:
            with self._metrics_lock:
                self.divergence_metrics["drift_warnings"] += 1
            logger.warning("[Federation] Significant drift divergence detected: %.4f", avg_drift)

        return avg_drift  # type: ignore[no-any-return]
