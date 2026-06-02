"""
Unit Tests for Phase 83 Multi-Shard Federation State Merging.
"""

from __future__ import annotations

import time

import pytest
from app.crawl_policy import get_crawl_policy
from app.federation_manager import FederationManager, ShardStateSnapshot
from app.semantic_world_state import get_world_state


@pytest.fixture
def clean_world_state():
    ws = get_world_state()
    # Reset state to clean bounds
    ws._evolved_schema = set()
    if hasattr(ws, "_topology") and hasattr(ws._topology, "_neighborhood_cohesion"):
        ws._topology._neighborhood_cohesion.clear()
    ws.regression.clear()
    return ws


@pytest.fixture
def clean_policy():
    policy = get_crawl_policy()
    policy._domains.clear()
    policy._global_active_fetches = 0
    return policy


def test_node_registration(clean_world_state):
    federation = FederationManager(clean_world_state)
    assert len(federation.registered_nodes) == 0

    federation.register_node("node-2", "shard-2")
    assert "node-2" in federation.registered_nodes
    assert federation.registered_nodes["node-2"]["shard_id"] == "shard-2"
    assert federation.registered_nodes["node-2"]["status"] == "active"


def test_export_local_state(clean_world_state, clean_policy):
    # Set up some local state
    state = clean_policy._get_state("example.com")
    state.consecutive_failures = 2
    state.total_fetches = 5
    state.last_fetch_time = time.time()

    clean_world_state._evolved_schema.add("title-price")

    federation = FederationManager(clean_world_state)
    snapshot = federation.export_local_state()

    assert isinstance(snapshot, ShardStateSnapshot)
    assert snapshot.node_id == federation.node_id
    assert "example.com" in snapshot.domain_reputation
    assert snapshot.domain_reputation["example.com"]["consecutive_failures"] == 2
    assert ["price", "title"] in [sorted(m) for m in snapshot.motifs]


def test_lww_domain_reputation_merge(clean_world_state, clean_policy):
    federation = FederationManager(clean_world_state)
    policy = clean_policy

    # Initialize local policy reputation
    local_state = policy._get_state("test-domain.com")
    local_state.consecutive_failures = 1
    local_state.total_fetches = 2
    local_state.last_fetch_time = 1000.0  # Old fetch time

    # Create remote snapshot with newer fetch time
    remote_rep = {
        "test-domain.com": {
            "consecutive_failures": 4,
            "total_fetches": 10,
            "cooldown_until": 2000.0,
            "last_update": 1005.0,  # Newer fetch time
        }
    }
    snapshot = ShardStateSnapshot(
        node_id="remote-node",
        shard_id="shard-2",
        timestamp=time.time(),
        transaction_id=1,
        domain_reputation=remote_rep,
    )

    report = federation.merge_remote_state(snapshot)
    assert report["merged_domains"] == 1

    # Verify that LWW was successfully applied
    merged_state = policy._get_state("test-domain.com")
    assert merged_state.consecutive_failures == 4
    assert merged_state.total_fetches == 10
    assert merged_state.cooldown_until == 2000.0
    assert merged_state.last_fetch_time == 1005.0


def test_motifs_union_merge(clean_world_state):
    federation = FederationManager(clean_world_state)
    clean_world_state._evolved_schema.add("title-price")

    snapshot = ShardStateSnapshot(
        node_id="remote-node",
        shard_id="shard-2",
        timestamp=time.time(),
        transaction_id=1,
        motifs=[["price", "rating"]],
    )

    report = federation.merge_remote_state(snapshot)
    assert report["merged_motifs"] == 1
    assert "price-rating" in clean_world_state._evolved_schema


def test_topological_affinity_consensus_merge(clean_world_state):
    federation = FederationManager(clean_world_state)

    if hasattr(clean_world_state, "_topology"):
        clean_world_state._topology._neighborhood_cohesion[("node-A", "node-B")] = 0.8

    snapshot = ShardStateSnapshot(
        node_id="remote-node",
        shard_id="shard-2",
        timestamp=time.time(),
        transaction_id=1,
        topology={"node-A:node-B": 0.4},
    )

    report = federation.merge_remote_state(snapshot)
    assert report["reconciled_topologies"] == 1

    # Topological consensus consensus should average: (0.8 + 0.4) / 2 = 0.6
    assert clean_world_state._topology._neighborhood_cohesion[("node-A", "node-B")] == pytest.approx(0.6)


def test_rejoin_transaction_delta_replays(clean_world_state):
    federation = FederationManager(clean_world_state)

    deltas = [
        {
            "action": "add_motif",
            "timestamp": 10.0,
            "payload": {"motif": "title-description"},
        },
        {
            "action": "record_failure",
            "timestamp": 12.0,
            "payload": {"domain": "bad-site.org", "fail_type": "anti_bot_block"},
        }
    ]

    report = federation.replay_deltas(deltas)
    assert report["received"] == 2
    assert report["replayed"] == 2
    assert report["failed"] == 0

    assert "title-description" in clean_world_state._evolved_schema
    # Check that failure was archived in regression state
    failures = clean_world_state.regression.get_failure_counts("bad-site.org")
    assert failures.get("anti_bot_block") == 1


def test_drift_divergence_metrics(clean_world_state):
    federation = FederationManager(clean_world_state)

    if hasattr(clean_world_state, "_topology"):
        clean_world_state._topology._neighborhood_cohesion[("node-A", "node-B")] = 0.9
        clean_world_state._topology._neighborhood_cohesion[("node-C", "node-D")] = 0.1

    snapshot = ShardStateSnapshot(
        node_id="remote-node",
        shard_id="shard-2",
        timestamp=time.time(),
        transaction_id=1,
        topology={"node-A:node-B": 0.7, "node-C:node-D": 0.2},
    )

    drift = federation.compute_drift_divergence(snapshot)
    # distance = (|0.9 - 0.7| + |0.1 - 0.2|) / 2 = (0.2 + 0.1) / 2 = 0.15
    assert abs(drift - 0.15) < 0.001
    assert federation.divergence_metrics["last_drift_score"] == 0.1500
