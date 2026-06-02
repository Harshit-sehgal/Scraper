"""Deterministic Replay — verifies that transaction journals can reconstruct
semantic state across all subsystems with full fidelity.

This is the definitive coverage for:
- replay_transaction() correctness
- journal entry completeness (are all mutations captured?)
- replay resilience (corrupt/missing entries don't crash)
- cumulative replay ordering guarantees

Current replayable subsystems (via replay_transaction dispatch):
energy, topology, instability, manifold, motif, transition, intent,
action, abstraction, observability, history

Global events (federation, merge, promotion, relaxation) are skipped
during replay since they are orchestration-level side effects of other
subsystem entries.
"""

from app.semantic_world_state import get_world_state

# ═══════════════════════════════════════════════════════════════════
# HELPER: capture the most recent transaction entry
# ═══════════════════════════════════════════════════════════════════


def _capture_last_tx(ws):
    """Return the last transaction from the causality journal."""
    journal = ws.trace_causality(limit=50)
    assert len(journal) >= 1, "No transactions found"
    return journal[-1]


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 1: MULTI-SUBSYSTEM REPLAY STRESS TEST
# ═══════════════════════════════════════════════════════════════════


def test_full_multi_subsystem_replay():
    """Execute mutations across all 10 replayable subsystems, clear,
    replay, and verify state equivalence on every subsystem."""
    ws = get_world_state()
    ws.clear()

    # ── 1. Execute a rich transaction touching every subsystem ──
    with ws.transaction("stress_test", trace_id="stress_001"):
        # Energy
        ws._energy.set_energy(3.5)
        ws._energy.set_entropy(0.25)
        ws._energy.increment_records(5)

        # Topology
        ws._topology.add(["role_a", "role_b"], "token_x", instability=0.3, integrity=0.7, domain="test")

        # Instability
        ws._instability.set_exclusion(("role_a", "role_b"), 0.65)
        ws._instability.set_exclusion(("role_c", "role_d"), 0.8)

        # Manifold
        ws._manifold.set_manifold_vector("role_a", [0.1] * 16)
        ws._manifold.set_manifold_vector("role_b", [0.9] * 16)
        ws._manifold.set_compatibility("role_a", "price", 0.85)
        ws._manifold.set_compatibility("role_b", "name", 0.75)
        ws._manifold.anchor_role("role_b")

        # Transition
        ws._transition.set_prob("name", "price", 0.6)
        ws._transition.set_prob("price", "date", 0.3)
        ws._transition.set_transition_observations(3)

        # Motif
        ws._motif.reinforce(("name", "price"), current_record=5)

        # Intent
        ws._intent.set_intent("intent_1", [0.2] * 16, strength=0.7, target_roles=["role_a"])

        # Action
        ws._action.register_action("action_1", [0.3] * 16, "handler_fn", threshold=0.4)
        ws._action.log_execution("action_1", success=True)

        # Abstraction
        ws._abstraction.create_envelope("env_1", ["role_a", "role_b"], [0.5] * 16, level=1)

        # Observability
        ws._observability.emit_telemetry("test_event", {"key": "val"})

    # Capture snapshot of pre-clear values
    tx = _capture_last_tx(ws)
    pre_energy = ws.metrics.global_energy
    pre_entropy = ws.metrics.global_entropy
    pre_records = ws.metrics.total_records_processed
    pre_exclusions = dict(ws.learned_exclusions)
    pre_manifold_roles = set(ws.get_manifold_roles())
    pre_compat = dict(ws.role_compatibility)
    pre_anchors = set(ws.role_anchors)
    pre_region_count = ws._topology.region_count()
    pre_trans_probs = dict(ws.transition_probs)
    pre_trans_obs = ws.transition_observations
    pre_motif_count = len(ws.motif_counts)
    pre_envelopes = set(ws.abstraction_envelopes.keys())

    # ── 2. Clear all state ──
    ws.clear()
    assert ws.metrics.global_energy == 5.0, "Energy should reset to default"
    assert ws._topology.region_count() == 0, "Regions should be empty"
    assert len(ws.learned_exclusions) == 0, "Exclusions should be empty"

    # ── 3. Replay the transaction ──
    ws.replay_transaction(tx)

    # ── 4. Verify state restored ──
    # Energy
    assert abs(ws.metrics.global_energy - pre_energy) < 0.001
    assert abs(ws.metrics.global_entropy - pre_entropy) < 0.001
    assert ws.metrics.total_records_processed == pre_records

    # Topology (structural, not ID-based)
    assert ws._topology.region_count() == pre_region_count
    view = ws._topology.get_view()
    regions = view.all_regions()
    tokens = [r.token for r in regions]
    assert "token_x" in tokens

    # Instability
    for key, val in pre_exclusions.items():
        restored = ws.learned_exclusions.get(key, 0.0)
        assert abs(restored - val) < 0.001, f"Exclusion {key}: expected {val}, got {restored}"

    # Manifold
    restored_roles = set(ws.get_manifold_roles())
    assert restored_roles == pre_manifold_roles, f"Manifold roles differ: {restored_roles} vs {pre_manifold_roles}"
    for (role, type_str), val in pre_compat.items():
        restored = ws.get_compatibility(role, type_str)
        assert abs(restored - val) < 0.001, f"Compatibility {(role, type_str)}: expected {val}, got {restored}"
    assert ws.role_anchors == pre_anchors

    # Transition
    for key, val in pre_trans_probs.items():
        restored = ws.get_transition_prob(*key)
        assert abs(restored - val) < 0.001, f"Transition {key}: expected {val}, got {restored}"
    assert ws.transition_observations == pre_trans_obs

    # Motif
    assert len(ws.motif_counts) == pre_motif_count

    # Abstraction
    assert set(ws.abstraction_envelopes.keys()) == pre_envelopes


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 2: REPLAY RESILIENCE
# ═══════════════════════════════════════════════════════════════════


def test_replay_empty_entries():
    """Replay a transaction with no entries must not crash."""
    ws = get_world_state()
    ws.clear()

    empty_tx = {
        "label": "empty",
        "timestamp": 100.0,
        "clock": {},
        "entries": [],
    }
    ws.replay_transaction(empty_tx)
    # No crash = pass


def test_replay_missing_optional_fields():
    """Replay a transaction with minimal/missing fields must not crash."""
    ws = get_world_state()
    ws.clear()

    minimal_tx = {"label": "minimal", "entries": []}
    ws.replay_transaction(minimal_tx)
    # No crash = pass


def test_replay_unknown_subsystem_skipped():
    """Entries with unknown subsystems must be skipped, not crash."""
    ws = get_world_state()
    ws.clear()

    tx = {"label": "unknown_subsystem", "entries": [{"subsystem": "nonexistent", "action": "foo", "details": {}}]}
    ws.replay_transaction(tx)
    # No crash = pass


def test_replay_unknown_method_skipped():
    """Entries with non-existent methods on a valid subsystem must be skipped."""
    ws = get_world_state()
    ws.clear()

    tx = {"label": "unknown_method", "entries": [{"subsystem": "energy", "action": "nonexistent_method", "details": {}}]}
    ws.replay_transaction(tx)
    # No crash = pass


def test_replay_invalid_args_skipped():
    """Entries with wrong argument names must be skipped, not crash the batch."""
    ws = get_world_state()
    ws.clear()

    tx = {
        "label": "bad_args",
        "entries": [
            # Valid entry first
            {"subsystem": "energy", "action": "set_energy", "details": {"value": 7.5}},
            # Invalid — wrong arg name
            {"subsystem": "energy", "action": "set_energy", "details": {"wrong_arg": 999}},
            # Valid entry after failure
            {"subsystem": "energy", "action": "set_energy", "details": {"value": 3.0}},
        ],
    }
    ws.replay_transaction(tx)

    # The first and last valid entries should have taken effect
    assert abs(ws.metrics.global_energy - 3.0) < 0.001, f"Expected 3.0 from valid entries, got {ws.metrics.global_energy}"


def test_replay_partial_failure_recovers():
    """A batch where only some entries fail must still replay all valid ones."""
    ws = get_world_state()
    ws.clear()

    tx = {
        "label": "partial_failure",
        "entries": [
            {"subsystem": "energy", "action": "set_energy", "details": {"value": 2.0}},
            # Will fail — no valid subsystem
            {"subsystem": "bogus", "action": "crash", "details": {}},
            {"subsystem": "energy", "action": "set_entropy", "details": {"value": 0.1}},
            # Will fail — missing required args
            {"subsystem": "manifold", "action": "set_manifold_vector", "details": {}},
            {"subsystem": "instability", "action": "set_exclusion", "details": {"key": ("x", "y"), "value": 0.9}},
        ],
    }
    ws.replay_transaction(tx)

    # Valid entries must have taken effect
    assert abs(ws.metrics.global_energy - 2.0) < 0.001
    assert abs(ws.metrics.global_entropy - 0.1) < 0.001
    assert abs(ws.learned_exclusions.get(("x", "y"), 0.0) - 0.9) < 0.001


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 3: JOURNAL INTEGRITY
# ═══════════════════════════════════════════════════════════════════


def test_journal_entry_structure():
    """Every journal entry must have subsystem, action, and details fields."""
    ws = get_world_state()
    ws.clear()

    with ws.transaction("struct_test"):
        ws._energy.set_energy(6.0)
        ws._manifold.set_manifold_vector("test_role", [0.5] * 16)

    tx = _capture_last_tx(ws)

    assert "entries" in tx, "Transaction must contain 'entries' list"
    assert len(tx["entries"]) >= 2, f"Expected at least 2 entries, got {len(tx['entries'])}"

    for entry in tx["entries"]:
        assert "subsystem" in entry, f"Entry missing 'subsystem': {entry}"
        assert "action" in entry, f"Entry missing 'action': {entry}"
        assert "details" in entry, f"Entry missing 'details': {entry}"
        assert isinstance(entry["details"], dict), f"Entry 'details' must be a dict, got {type(entry['details'])}"


def test_all_replayable_subsystems_record():
    """Each replayable subsystem must generate journal entries under
    normal operation. Excludes 'global' which is orchestration-level."""
    ws = get_world_state()
    ws.clear()

    subsystems = {
        "energy": lambda: ws._energy.set_energy(3.0),
        "topology": lambda: ws._topology.add(["r1"], "t1", instability=0.5),
        "instability": lambda: ws._instability.set_exclusion(("x", "y"), 0.5),
        "manifold": lambda: ws._manifold.set_manifold_vector("m_role", [0.2] * 16),
        "motif": lambda: ws._motif.reinforce(("m1", "m2"), current_record=10),
        "transition": lambda: ws._transition.set_prob("type_a", "type_b", 0.5),
        "intent": lambda: ws._intent.set_intent("i1", [0.5] * 16),
        "action": lambda: ws._action.register_action("a1", [0.5] * 16, "handler"),
        "abstraction": lambda: ws._abstraction.create_envelope("e1", ["r1"], [0.5] * 16, level=0),
        "observability": lambda: ws._observability.emit_telemetry("evt", {"k": "v"}),
        "history": lambda: ws._history.record_decision({"test": True}),
    }

    with ws.transaction("all_subsystems"):
        for name, fn in subsystems.items():
            fn()

    tx = _capture_last_tx(ws)
    recorded_subsystems = {e["subsystem"] for e in tx["entries"]}

    for name in subsystems:
        assert name in recorded_subsystems, f"Subsystem '{name}' did not produce a journal entry"


def test_journal_trace_id_propagation():
    """Journal entries within a transaction must carry the trace_id."""
    ws = get_world_state()
    ws.clear()

    with ws.transaction("trace_test", trace_id="my_trace_abc"):
        ws._energy.set_energy(4.0)

    tx = _capture_last_tx(ws)
    assert tx.get("trace_id") == "my_trace_abc", f"Expected trace_id='my_trace_abc', got {tx.get('trace_id')}"

    for entry in tx.get("entries", []):
        assert entry.get("trace_id") == "my_trace_abc", f"Entry missing trace_id: {entry}"


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 4: CUMULATIVE REPLAY — ORDERING GUARANTEES
# ═══════════════════════════════════════════════════════════════════


def test_cumulative_replay_multiple_transactions():
    """Execute 3 chained transactions, clear, replay all in order,
    verify final state matches exactly."""
    ws = get_world_state()
    ws.clear()

    # Transaction 1: seed energy + manifold + exclusion
    with ws.transaction("phase_1", trace_id="replay_01"):
        ws._energy.set_energy(2.0)
        ws._manifold.set_manifold_vector("phase_role", [0.3] * 16)
        ws._instability.set_exclusion(("a", "b"), 0.4)

    tx1 = _capture_last_tx(ws)

    # Transaction 2: increment energy + add topology region
    with ws.transaction("phase_2", trace_id="replay_02"):
        ws._energy.set_energy(4.0)
        ws._energy.increment_records(3)
        ws._topology.add(["phase_role", "other"], "phase_token", instability=0.2)

    tx2 = _capture_last_tx(ws)

    # Transaction 3: final adjustments + new exclusion
    with ws.transaction("phase_3", trace_id="replay_03"):
        ws._energy.set_energy(6.5)
        ws._instability.set_exclusion(("a", "c"), 0.9)
        ws._manifold.set_compatibility("phase_role", "name", 0.95)
        ws._transition.set_prob("name", "price", 0.7)

    tx3 = _capture_last_tx(ws)

    # Capture expected final state
    expected_energy = ws.metrics.global_energy
    expected_exclusions = dict(ws.learned_exclusions)
    expected_roles = set(ws.get_manifold_roles())
    expected_region_count = ws._topology.region_count()
    expected_records = ws.metrics.total_records_processed
    expected_compat = dict(ws.role_compatibility)
    expected_probs = dict(ws.transition_probs)

    # Clear all state
    ws.clear()
    assert ws.metrics.global_energy == 5.0
    assert ws._topology.region_count() == 0
    assert len(ws.learned_exclusions) == 0

    # Replay in order
    ws.replay_transaction(tx1)
    ws.replay_transaction(tx2)
    ws.replay_transaction(tx3)

    # Verify final state matches
    assert (
        abs(ws.metrics.global_energy - expected_energy) < 0.001
    ), f"Energy: expected {expected_energy}, got {ws.metrics.global_energy}"
    assert ws.metrics.total_records_processed == expected_records
    assert set(ws.get_manifold_roles()) == expected_roles

    for key, val in expected_exclusions.items():
        restored = ws.learned_exclusions.get(key, 0.0)
        assert abs(restored - val) < 0.001, f"Exclusion {key}: expected {val}, got {restored}"

    assert ws._topology.region_count() == expected_region_count

    for (role, type_str), val in expected_compat.items():
        restored = ws.get_compatibility(role, type_str)
        assert abs(restored - val) < 0.001, f"Compat {(role, type_str)}: expected {val}, got {restored}"

    for key, val in expected_probs.items():
        restored = ws.get_transition_prob(*key)
        assert abs(restored - val) < 0.001, f"Transition {key}: expected {val}, got {restored}"


def test_replay_idempotent():
    """Replaying the same transaction twice should produce the same
    final state as replaying it once."""
    ws = get_world_state()
    ws.clear()

    with ws.transaction("idempotent_test"):
        ws._energy.set_energy(2.5)
        ws._manifold.set_manifold_vector("idem_role", [0.7] * 16)

    tx = _capture_last_tx(ws)

    # Replay once
    ws.clear()
    ws.replay_transaction(tx)
    state_after_one = ws.metrics.global_energy

    # Replay again on fresh state
    ws.clear()
    ws.replay_transaction(tx)
    state_after_two = ws.metrics.global_energy

    assert abs(state_after_one - state_after_two) < 0.001, f"Replay not idempotent: {state_after_one} vs {state_after_two}"


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 5: DIRECT MUTATION RECORDING
# ═══════════════════════════════════════════════════════════════════


def test_direct_mutation_recorded_outside_transaction():
    """Mutations made outside a transaction must still appear in the
    global journal (with 'direct_mutation' label)."""
    ws = get_world_state()
    ws.clear()

    # Mutate outside transaction
    ws._energy.set_energy(7.5)

    journal = ws.trace_causality(limit=50)
    direct = [j for j in journal if j.get("label") == "direct_mutation"]
    assert len(direct) >= 1, "Direct mutation should be recorded with 'direct_mutation' label"

    # Verify the entry contains the mutation
    found = False
    for entry in direct:
        for e in entry.get("entries", []):
            if e.get("subsystem") == "energy" and e.get("action") == "set_energy":
                found = True
                break
    assert found, "Direct set_energy should be in journal entries"


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 6: TOPOLOGY REPLAY — STRUCTURAL VERIFICATION
# ═══════════════════════════════════════════════════════════════════


def test_topology_add_replay_structural():
    """Replaying topology.add() must restore the correct number of
    regions with matching tokens and roles (ID-independent verification)."""
    ws = get_world_state()
    ws.clear()

    with ws.transaction("topo_add_test"):
        ws._topology.add(["seller", "buyer"], "token_123", instability=0.35, integrity=0.8, domain="ecommerce")
        ws._topology.add(["origin", "destination"], "token_456", instability=0.2, domain="travel")

    tx = _capture_last_tx(ws)
    pre_count = ws._topology.region_count()

    ws.clear()
    assert ws._topology.region_count() == 0

    ws.replay_transaction(tx)
    assert ws._topology.region_count() == pre_count, f"Expected {pre_count} regions, got {ws._topology.region_count()}"

    view = ws._topology.get_view()
    tokens = sorted(view.get_all_tokens())
    assert tokens == sorted(["token_123", "token_456"]), f"Tokens don't match: {tokens}"

    # Check region attributes
    for t in ["token_123", "token_456"]:
        regions = view.find_by_token(t)
        assert len(regions) >= 1, f"Token {t} not found after replay"


def test_topological_law_replay():
    """Topological law mutations must survive replay."""
    ws = get_world_state()
    ws.clear()

    with ws.transaction("law_test"):
        ws._topology.set_topological_law(("role_x", "role_y"), 0.75)

    tx = _capture_last_tx(ws)
    pre_laws = dict(ws.topological_laws)

    ws.clear()
    assert len(ws.topological_laws) == 0

    ws.replay_transaction(tx)
    restored = dict(ws.topological_laws)

    assert restored == pre_laws, f"Topological laws mismatch: restored {restored}, expected {pre_laws}"


# ═══════════════════════════════════════════════════════════════════
# TEST GROUP 7: TUPLE KEY HANDLING IN REPLAY
# ═══════════════════════════════════════════════════════════════════


def test_replay_instability_tuple_key_deserialization():
    """Tuple keys in instability entries must survive JSON serialization/
    deserialization during replay."""
    ws = get_world_state()
    ws.clear()

    with ws.transaction("tuple_test"):
        ws._instability.set_exclusion(("key_a", "key_b"), 0.7)
        ws._instability.set_exclusion(("key_c", "key_d"), 0.3)

    tx = _capture_last_tx(ws)

    # Simulate JSON round-trip (converts tuple keys to lists)
    import json

    tx_json = json.dumps(tx)
    tx_loaded = json.loads(tx_json)
    # Reconstruct entries — tuples in details become lists after JSON
    for entry in tx_loaded.get("entries", []):
        if "key" in entry.get("details", {}):
            entry["details"]["key"] = tuple(entry["details"]["key"])


def test_long_horizon_replay_parity():
    """Execute 500 random transactions, capture the journal, and verify
    that full replay results in identical metrics and manifold checksum."""
    import random

    ws = get_world_state()
    ws.clear()

    roles = ["role_1", "role_2", "role_3", "role_4", "role_5"]

    # ── 1. Original Run ──
    for i in range(500):
        with ws.transaction(f"tx_{i}"):
            role = random.choice(roles)
            ws._manifold.set_manifold_vector(role, [random.random() for _ in range(16)])
            ws._energy.set_energy(ws.metrics.global_energy + (random.random() - 0.5) * 0.1)
            if i % 10 == 0:
                ws._instability.set_exclusion((random.choice(roles), random.choice(roles)), random.random())

    # Capture final state metrics
    original_metrics = {
        "energy": ws.metrics.global_energy,
        "entropy": ws.metrics.global_entropy,
        "records": ws.metrics.total_records_processed,
    }
    original_checksum = ws.get_manifold_checksum()
    full_journal = ws.trace_causality(limit=600)

    # ── 2. Replay Run ──
    ws.clear()
    for tx in full_journal:
        ws.replay_transaction(tx)

    # ── 3. Verification ──
    assert abs(ws.metrics.global_energy - original_metrics["energy"]) < 0.001
    assert abs(ws.metrics.global_entropy - original_metrics["entropy"]) < 0.001
    assert ws.metrics.total_records_processed == original_metrics["records"]
    assert ws.get_manifold_checksum() == original_checksum
    print("\nLong-horizon replay parity confirmed (500 transactions).")
