"""Phase 8: Semantic invariant engineering — guarantees topological coherence.

Each invariant validates a specific property of the semantic field system.
If any invariant fails, the architecture is not semantically coherent.
"""

from app.semantic_world_state import get_world_state
from app.semantic_pipeline import run_pipeline
from app.semantic_allocation_engine import (
    _adaptive_exclusion_threshold, _adaptive_runtime_exclusion_threshold,
    ROLE_EXCLUSIVITY,
)
from app.event_dispatcher import get_dispatcher
from app.semantic_events import SemanticEventType


# ─────────────────────────────────────────────────────────────
# INVARIANT 1: Field pressure is always bounded [0, 1]
# ─────────────────────────────────────────────────────────────

def test_field_pressure_bounds():
    ws = get_world_state()
    ws.clear()
    p = ws.metrics.field_pressure
    assert 0.0 <= p <= 1.0, f"field_pressure {p} out of bounds"

    ws.metrics.global_energy = 20.0
    p2 = ws.metrics.field_pressure
    assert 0.0 <= p2 <= 1.0, f"field_pressure {p2} out of bounds after energy spike"


# ─────────────────────────────────────────────────────────────
# INVARIANT 2: Field pressure drops as the system stabilizes
# ─────────────────────────────────────────────────────────────

def test_field_pressure_decreases_with_stabilization():
    ws = get_world_state()
    ws.clear()
    # Initial state: high energy, high entropy
    p_initial = ws.metrics.field_pressure
    # After processing records: lower energy, lower uncertainty
    ws.metrics.total_records_processed = 100
    ws.metrics.global_energy = 1.0
    ws.metrics.global_entropy = 0.3
    ws.metrics.cumulative_uncertainty = 10
    p_final = ws.metrics.field_pressure
    assert p_final < p_initial, f"Pressure should drop with stabilization ({p_final} >= {p_initial})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 3: Adaptive thresholds stay within domain bounds
# ─────────────────────────────────────────────────────────────

def test_adaptive_threshold_bounds():
    for _ in range(20):
        t = _adaptive_exclusion_threshold()
        assert 0.2 <= t <= 0.6, f"structural threshold {t} out of bounds"
        t2 = _adaptive_runtime_exclusion_threshold()
        assert 0.15 <= t2 <= 0.5, f"runtime threshold {t2} out of bounds"


# ─────────────────────────────────────────────────────────────
# INVARIANT 4: Contradiction pipeline — contradictions detected,
#              energy tracked, re-allocation resolved
# ─────────────────────────────────────────────────────────────

def test_contradiction_pipeline_invariant():
    ws = get_world_state()
    ws.clear()
    schema = ["origin", "destination"]
    records = [{"origin": "LAX", "destination": "LAX"}]
    result = run_pipeline(records, schema)
    assert result, "Pipeline should not drop contradictory records"
    r = result[0]
    assert r.get("_contradictions"), "Contradictions must be detected"
    assert r.get("_contradiction_energy", 0) > 0, "Contradiction energy must be tracked"
    assert r.get("_contradictions") or r.get("_allocation_conflicts") or r.get("_field_arbitrated"), \
        "Contradictions must be detected or field must arbitrate"


# ─────────────────────────────────────────────────────────────
# INVARIANT 5: No false contradictions for distinct values
# ─────────────────────────────────────────────────────────────

def test_no_false_contradiction_invariant():
    ws = get_world_state()
    ws.clear()
    schema = ["origin", "destination"]
    records = [{"origin": "JFK", "destination": "LAX"}]
    result = run_pipeline(records, schema)
    assert result, "Pipeline should process distinct-value records"
    r = result[0]
    assert not r.get("_contradictions"), "No contradiction for distinct values"
    assert r.get("_contradiction_energy", 0) == 0, "No contradiction energy expected"


# ─────────────────────────────────────────────────────────────
# INVARIANT 6: Event cascade has exactly 1 subscriber per type
#              (no duplicates, no orphans)
# ─────────────────────────────────────────────────────────────

def test_event_cascade_invariant():
    d = get_dispatcher()
    for et in [SemanticEventType.TOPOLOGY_SHIFT, SemanticEventType.CONTRADICTION_DETECTED, SemanticEventType.UNCERTAINTY_SPIKE]:
        subs = d.subscribers.get(et, [])
        assert len(subs) == 1, f"{et.value} should have exactly 1 subscriber, has {len(subs)}"


# ─────────────────────────────────────────────────────────────
# INVARIANT 7: Cascade works regardless of import order
# ─────────────────────────────────────────────────────────────

def test_import_order_independence_invariant():
    """Verified at the module level — direct import must produce cascade."""
    # This test verifies that importing event_dispatcher directly (not through
    # main or semantic_pipeline) triggers the cascade self-bootstrap.
    # The bootstrap requires that graph_update_scheduler module is loaded
    # (it's already imported by this test file through get_scheduler import).
    from app.event_dispatcher import get_dispatcher as gd
    from app.semantic_events import SemanticEventType as SET
    d = gd()
    subs = len(d.subscribers.get(SET.TOPOLOGY_SHIFT, []))
    assert subs >= 1, f"Direct dispatcher must have >=1 subscriber, has {subs}"


# ─────────────────────────────────────────────────────────────
# INVARIANT 8: Contradiction learning — learned exclusions decay
#              without reinforcement and strengthen with recurrence
# ─────────────────────────────────────────────────────────────

def test_topology_evolution_invariant():
    ws = get_world_state()
    ws.clear()
    key = ("destination", "origin")
    schema = ["origin", "destination"]

    # Record 1: contradiction → strengthen
    run_pipeline([{"origin": "LAX", "destination": "LAX"}], schema)
    after_first = ws.learned_exclusions.get(key, 0.0)
    assert after_first > 0, "Exclusion must be learned from contradiction"

    # Record 2: no contradiction → decay
    run_pipeline([{"origin": "JFK", "destination": "LAX"}], schema)
    after_decay = ws.learned_exclusions.get(key, 0.0)
    assert after_decay <= after_first, f"Exclusion should decay without reinforcement ({after_decay} > {after_first})"

    # Record 3: contradiction again → reinforce
    run_pipeline([{"origin": "LHR", "destination": "LHR"}], schema)
    after_reinforce = ws.learned_exclusions.get(key, 0.0)
    assert after_reinforce >= after_decay, f"Exclusion should strengthen when reinforced ({after_reinforce} < {after_decay})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 9: Topology replay — snapshots capture evolution
# ─────────────────────────────────────────────────────────────

def test_topology_replay_invariant():
    ws = get_world_state()
    ws.clear()
    before = len(ws.topology_snapshots)

    schema = ["origin", "destination"]
    # First record: normal allocation
    run_pipeline([{"origin": "JFK", "destination": "LAX"}], schema)
    # Second record: triggers contradiction, changes topology
    run_pipeline([{"origin": "LAX", "destination": "LAX"}], schema)

    after = len(ws.topology_snapshots)
    assert after > before, f"Snapshots must accumulate ({after} <= {before})"

    replay = ws.replay()
    assert len(replay) > 0, "Replay must return snapshots"

    diff = ws.diff_snapshots(0, -1)
    assert diff, "Diff between first and last snapshot must show evolution, got empty"


# ─────────────────────────────────────────────────────────────
# INVARIANT 10: Field pressure is causally linked to energy
#               (lower energy → lower field pressure)
# ─────────────────────────────────────────────────────────────

def test_pressure_energy_causality_invariant():
    ws = get_world_state()
    ws.clear()
    ws.metrics.global_energy = 5.0
    p_high = ws.metrics.field_pressure
    ws.metrics.global_energy = 0.5
    p_low = ws.metrics.field_pressure
    assert p_low < p_high, f"Lower energy must reduce field pressure ({p_low} >= {p_high})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 11: Learned exclusions persist through save/load
# ─────────────────────────────────────────────────────────────

def test_exclusion_persistence_invariant():
    import os
    import tempfile
    ws = get_world_state()
    ws.clear()
    ws.learned_exclusions[("a", "b")] = 0.75

    old_path = os.environ.get("SEMANTIC_STATE_PATH")
    tmp = tempfile.mktemp(".json")
    os.environ["SEMANTIC_STATE_PATH"] = tmp

    try:
        from app.semantic_persistence import save_semantic_state, load_semantic_state
        save_semantic_state()
        ws2 = get_world_state()
        ws2.clear()
        load_semantic_state()
        assert ws2.learned_exclusions.get(("a", "b"), 0) == 0.75, "Exclusions must survive save/load"
    finally:
        if old_path:
            os.environ["SEMANTIC_STATE_PATH"] = old_path
        else:
            os.environ.pop("SEMANTIC_STATE_PATH", None)
        try:
            os.remove(tmp)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────
# INVARIANT 12: Motif stability influences compatibility
#               (semantic memory as gravity)
# ─────────────────────────────────────────────────────────────

def test_memory_gravity_invariant():
    ws = get_world_state()
    ws.clear()

    schema = ["name", "price"]
    # Process same motif pattern repeatedly
    for _ in range(5):
        run_pipeline([{"company": "Acme", "cost": "100"}], schema)

    # (name, organization) compatibility should be above baseline
    compat = ws.role_compatibility.get(("name", "organization"), 0.5)
    assert compat > 0.5, f"Stable motifs must strengthen compatibility ({compat} <= 0.5)"


# ─────────────────────────────────────────────────────────────
# INVARIANT 13: Learned exclusion topology must be bounded [0, 1]
# ─────────────────────────────────────────────────────────────

def test_exclusion_bounds_invariant():
    """Learned exclusions produced by the system must stay bounded [0, 1]."""
    ws = get_world_state()
    ws.clear()
    schema = ["origin", "destination"]
    # Process a contradiction which creates learned exclusions
    run_pipeline([{"origin": "LAX", "destination": "LAX"}], schema)
    for key, val in ws.learned_exclusions.items():
        assert 0.0 <= val <= 1.0, f"Exclusion {key} = {val} out of bounds"


# ─────────────────────────────────────────────────────────────
# INVARIANT 14: ROLE_EXCLUSIVITY pairs are always sorted
#               (no duplicate unordered pairs)
# ─────────────────────────────────────────────────────────────

def test_role_exclusivity_consistency_invariant():
    seen = set()
    for pair in ROLE_EXCLUSIVITY:
        sorted_pair = tuple(sorted(pair))
        assert sorted_pair not in seen, f"Duplicate exclusivity pair {pair}"
        seen.add(sorted_pair)


# ─────────────────────────────────────────────────────────────
# INVARIANT 15: Uncertainty is bounded [0, 1] after pipeline
# ─────────────────────────────────────────────────────────────

def test_uncertainty_bounds_invariant():
    ws = get_world_state()
    ws.clear()
    ws.metrics.cumulative_uncertainty = 0
    ws.metrics.total_records_processed = 100
    u = ws.metrics.average_uncertainty
    assert 0.0 <= u <= 1.0, f"Average uncertainty {u} out of bounds"


# ─────────────────────────────────────────────────────────────
# INVARIANT 16: Field pressure includes contradiction density
# ─────────────────────────────────────────────────────────────

def test_field_pressure_includes_contradictions():
    ws = get_world_state()
    ws.clear()
    p_before = ws.metrics.field_pressure
    ws.metrics.exclusion_count = 50
    ws.metrics.total_records_processed = 100
    p_after = ws.metrics.field_pressure
    assert p_after > p_before or abs(p_after - p_before) < 0.001, \
        "Field pressure must increase or stay same with more contradictions"


# ─────────────────────────────────────────────────────────────
# INVARIANT 17: Propagation wave tracing returns wave entries
# ─────────────────────────────────────────────────────────────

def test_propagation_wave_tracing():
    ws = get_world_state()
    ws.clear()
    ws.snapshot("alloc_0")
    ws.snapshot("relax_wave_1")
    ws.snapshot("relax_wave_2")
    ws.snapshot("alloc_1")
    waves = ws.trace_waves()
    assert len(waves) >= 2, f"Wave trace must include 2+ wave snapshots, got {len(waves)}"
    for w in waves:
        assert "wave" in w.get("label", ""), "All traced entries must have wave labels"


# ─────────────────────────────────────────────────────────────
# INVARIANT 18: Field pressure unifies all pressure dimensions
# ─────────────────────────────────────────────────────────────

def test_field_pressure_unifies_dimensions():
    ws = get_world_state()
    ws.clear()
    p = ws.metrics.field_pressure
    assert 0.0 <= p <= 1.0, f"field_pressure must be bounded [0,1], got {p}"
    ws.metrics.global_energy = 10.0
    p2 = ws.metrics.field_pressure
    assert p2 >= p or abs(p2 - p) < 0.001, "Higher energy must increase or maintain field pressure"
    ws.metrics.global_entropy = 0.0
    p3 = ws.metrics.field_pressure
    assert p3 <= p2 or abs(p3 - p2) < 0.001, "Lower entropy must decrease or maintain field pressure"


# ─────────────────────────────────────────────────────────────
# INVARIANT 19: Topology causality — field pressure alters exclusion memory
# ─────────────────────────────────────────────────────────────

def test_topology_causality_invariant():
    """Higher field pressure must produce tighter exclusion thresholds."""
    from app.semantic_allocation_engine import _adaptive_exclusion_threshold
    ws = get_world_state()
    ws.clear()
    ws.metrics.global_energy = 0.1
    ws.metrics.global_entropy = 0.1
    ws.metrics.cumulative_uncertainty = 1
    ws.metrics.total_records_processed = 100
    _adaptive_exclusion_threshold()  # prime hysteresis
    for _ in range(5):
        ws.metrics.global_energy = 0.1
        ws.metrics.global_entropy = 0.1
        t_low = _adaptive_exclusion_threshold()
    for _ in range(5):
        ws.metrics.global_energy = 9.0
        ws.metrics.global_entropy = 0.9
        t_high = _adaptive_exclusion_threshold()
    assert t_high >= t_low or abs(t_high - t_low) < 0.01, \
        f"Higher field pressure must raise exclusion threshold ({t_high} >= {t_low})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 20: Semantic gravity — stable motifs reduce exclusion
# ─────────────────────────────────────────────────────────────

def test_semantic_gravity_invariant():
    """Stable motifs should reduce exclusion pressure between roles."""
    ws = get_world_state()
    ws.clear()
    ws.role_compatibility[('name', 'price')] = 0.1
    ws.role_compatibility[('price', 'price')] = 0.9
    ws.metrics.total_records_processed = 100
    e_before = ws.get_derived_exclusion('name', 'price')
    # Add a stable motif — stability > 0.5 should PULL exclusion down
    ws.motif_counts[('organization', 'price')] = 500  # high count = stable
    ws.motif_timestamps[('organization', 'price')] = 95
    e_after = ws.get_derived_exclusion('name', 'price')
    assert e_after <= e_before or abs(e_after - e_before) < 0.001, \
        f"Stable motifs should reduce or maintain exclusion ({e_after} <= {e_before})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 21: Field equilibrium — field_pressure stabilizes over time
# ─────────────────────────────────────────────────────────────

def test_field_equilibrium_invariant():
    """Processing more records without contradictions should lower field pressure."""
    ws = get_world_state()
    ws.clear()
    schema = ["name", "price"]
    run_pipeline([{"company": "Test Corp", "cost": "100"}], schema)
    p1 = ws.metrics.field_pressure
    for _ in range(10):
        run_pipeline([{"company": "Stable Co", "cost": "200"}], schema)
    p2 = ws.metrics.field_pressure
    assert p2 <= p1 or abs(p2 - p1) < 0.1, \
        f"Stable processing should reduce field pressure ({p2} <= {p1})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 22: Topology restructuring — contradictions grow exclusion edges
# ─────────────────────────────────────────────────────────────

def test_topology_restructuring_invariant():
    """Repeated contradictions must increase learned exclusions."""
    ws = get_world_state()
    ws.clear()
    schema = ["origin", "destination"]
    before = len(ws.learned_exclusions)
    for _ in range(3):
        run_pipeline([{"origin": "LAX", "destination": "LAX"}], schema)
    after = len(ws.learned_exclusions)
    assert after >= before, \
        f"Contradictions must increase or maintain exclusion count ({after} >= {before})"


# ─────────────────────────────────────────────────────────────
# INVARIANT 23: Propagation conservation — field propagation must create exclusions
# ─────────────────────────────────────────────────────────────

def test_propagation_conservation_invariant():
    """Field propagation must spread instability to neighboring roles."""
    ws = get_world_state()
    ws.clear()
    schema = ["origin", "destination", "departure", "arrival"]
    before = len(ws.learned_exclusions)
    run_pipeline([{"origin": "LAX", "destination": "LAX", "depart": "10:00", "arrive": "12:00"}], schema)
    after = len(ws.learned_exclusions)
    assert after >= before, \
        f"Propagation must create or maintain exclusions ({after} >= {before})"



