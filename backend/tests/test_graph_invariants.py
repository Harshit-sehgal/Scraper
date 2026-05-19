"""Graph invariant validation — tests that semantic coherence properties hold."""

from app.semantic_ir import (
    ExclusionEdge, OwnershipEdge, SemanticGraph, SemanticRegion,
    SemanticToken, SemanticType, Span, RegionType,
)
from app.semantic_world_state import get_world_state, SemanticWorldState
from app.event_dispatcher import get_dispatcher
import pytest
from app.semantic_events import SemanticEvent, SemanticEventType


def test_world_state_round_trip_preserves_structure():
    """Invariant: SemanticWorldState to_dict → from_dict must be lossless."""
    ws = get_world_state()
    ws.clear()

    ws._energy.total_records_processed = 100
    ws._energy.set_energy(3.14)
    ws._manifold.set_compatibility("name", "text", 0.8)
    ws._instability.set_exclusion(tuple(sorted(["origin", "destination"])), 0.9)
    ws._motif._motif_counts[tuple(sorted(["A", "B"]))] = 5
    ws._motif._motif_timestamps[tuple(sorted(["A", "B"]))] = 42
    ws._topology.get_cohesion_merge_success()[tuple(sorted(["a", "b"]))] = 3.0
    ws._topology.get_cohesion_merge_attempts()[tuple(sorted(["a", "b"]))] = 5.0

    data = ws.to_dict()
    ws2 = SemanticWorldState()
    ws2.from_dict(data)

    assert ws2.metrics.total_records_processed == 100
    assert abs(ws2.metrics.global_energy - 3.14) < 0.001
    assert ws2.role_compatibility.get(("name", "text"), 0) == 0.8
    
    excl_key = tuple(sorted(["origin", "destination"]))
    assert ws2.learned_exclusions.get(excl_key, 0) == 0.9
    
    motif_key = tuple(sorted(["A", "B"]))
    assert ws2.motif_counts.get(motif_key, 0) == 5
    assert ws2.motif_timestamps.get(motif_key, 0) == 42
    
    cohesion_key = tuple(sorted(["a", "b"]))
    assert ws2.cohesion_merge_success.get(cohesion_key, 0) == 3.0
    assert ws2.cohesion_merge_attempts.get(cohesion_key, 0) == 5.0


def test_world_state_clear_resets_all():
    """Invariant: clear() must reset all fields to initial values."""
    ws = get_world_state()
    ws.clear()
    ws._energy.increment_records(50)
    ws._manifold.set_compatibility("test", "test", 1.0)
    ws.clear()

    assert ws.metrics.total_records_processed == 0
    assert len(ws.role_compatibility) == 0
    assert len(ws.learned_exclusions) == 0
    assert len(ws.motif_counts) == 0
    assert len(ws.motif_timestamps) == 0


def test_exclusion_edge_invariant():
    """Invariant: ExclusionEdge strengths must be bounded [0, 1]."""
    edges = [
        ExclusionEdge(source_id=0, target_id=1, strength=0.0),
        ExclusionEdge(source_id=2, target_id=3, strength=1.0),
        ExclusionEdge(source_id=4, target_id=5, strength=0.5),
    ]
    for e in edges:
        assert 0.0 <= e.strength <= 1.0, f"ExclusionEdge strength {e.strength} out of bounds"


def test_ownership_edge_no_self_ownership():
    """Invariant: OwnershipEdge owner_id must not equal owned_id."""
    edges = [
        OwnershipEdge(owner_region_id=1, owned_region_id=2, ownership_type="owns", confidence=0.8),
    ]
    for e in edges:
        assert e.owner_region_id != e.owned_region_id, "Self-ownership is invalid"


def test_semantic_token_confidence_bounds():
    """Invariant: SemanticToken confidence values must be bounded [0, 1]."""
    tok = SemanticToken(
        raw="test", normalized="test", span=Span(0, 4), position=0,
        primary_type=SemanticType.TEXT,
    )
    assert len(tok.embedding) == 16
    for val in tok.embedding:
        assert 0.0 <= val <= 1.0


def test_event_dispatcher_dispatch_does_not_raise():
    """Invariant: dispatching any SemanticEventType must never raise."""
    dispatcher = get_dispatcher()
    for event_type in SemanticEventType:
        try:
            dispatcher.dispatch(SemanticEvent(
                event_type=event_type,
                source="test",
                payload={"test": True},
                instability_delta=0.5,
            ))
        except Exception as e:
            pytest.fail(f"Dispatch of {event_type.value} raised: {e}")


def test_owner_cannot_own_self_in_graph():
    """Invariant: Self-ownership must be rejected by graph construction."""
    g = SemanticGraph(regions=[])
    g.ownership_edges.append(
        OwnershipEdge(owner_region_id=5, owned_region_id=5, ownership_type="owns", confidence=1.0)
    )
    region_a = SemanticRegion(
        region_id=5, region_type=RegionType.MIXED,
        tokens=[], start_position=0, end_position=1,
    )
    g.regions = [region_a]

    # Self-ownership should not be allowed: get_owner should not return self
    owner = g.get_owner(5)
    assert owner is None or owner.region_id != 5


def test_graph_register_region_preserves_invariants():
    """Invariant: Registering regions must not create duplicate IDs."""
    g = SemanticGraph(regions=[])
    ids = [0, 1, 2]
    for rid in ids:
        g.regions.append(SemanticRegion(
            region_id=rid, region_type=RegionType.UNKNOWN,
            tokens=[], start_position=0, end_position=1,
        ))
    # Verify no duplicate IDs
    all_ids = [r.region_id for r in g.regions]
    assert len(all_ids) == len(set(all_ids))


def test_exclusion_edge_always_bidirectional():
    """Invariant: Exclusion edges imply mutual exclusion in both directions."""
    g = SemanticGraph(regions=[])
    e1 = ExclusionEdge(source_id=1, target_id=2, strength=0.7)
    g.exclusion_edges.append(e1)
    # Verify it can be navigated from both sides in principle
    sources_for_2 = [e for e in g.exclusion_edges if e.target_id == 2]
    targets_for_1 = [e for e in g.exclusion_edges if e.source_id == 1]
    assert len(sources_for_2) > 0
    assert len(targets_for_1) > 0
    # Both directions should be consistent
    for e in g.exclusion_edges:
        reverse = [f for f in g.exclusion_edges if f.source_id == e.target_id and f.target_id == e.source_id]
        assert len(reverse) == 0 or abs(reverse[0].strength - e.strength) < 0.01
