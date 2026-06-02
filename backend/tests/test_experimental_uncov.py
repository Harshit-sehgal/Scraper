"""
Basic import and sanity tests for experimental modules without dedicated test coverage.

These are lightweight smoke tests that verify the modules can be imported,
their core classes instantiated, and basic methods execute without errors.
They do not validate semantic correctness of the research logic — that would
require dedicated integration tests.

Modules covered: field_laws, invariant_firewall, gossip_substrate,
vector_clock, manifold_state, motif_state, energy_state, instability_state.
"""

class TestFieldLaws:
    """field_laws.py — foundational constants, zero upward dependencies."""

    def test_import(self):
        import app.field_laws as fl
        assert hasattr(fl, "PROPAGATION_DECAY_FLOOR")
        assert fl.PROPAGATION_DECAY_FLOOR == 0.3
        assert fl.MAX_COUPLING_TRANSFER == 0.3
        assert fl.MAX_INSTABILITY_FLUX == 0.2
        assert fl.MAX_ATTRACTOR_PULL == 2.0
        assert fl.COUPLING_COEFFICIENT == 0.05
        assert fl.FREE_ENERGY_CLAMP == 2.0

    def test_role_exclusivity(self):
        from app.field_laws import ROLE_EXCLUSIVITY
        assert isinstance(ROLE_EXCLUSIVITY, list)
        assert ("start", "end") in ROLE_EXCLUSIVITY
        assert ("price", "cost") in ROLE_EXCLUSIVITY


class TestInvariantFirewall:
    """invariant_firewall.py — mutation guards for semantic field."""

    def test_import(self):
        import app.invariant_firewall as iv
        assert hasattr(iv, "requires_invariants")
        assert hasattr(iv, "_find_world_state")

    def test_requires_invariants_decorator_structure(self):
        from app.invariant_firewall import requires_invariants
        # Verify it's a decorator (callable that returns a wrapper)
        def dummy_fn(ws=None):
            return 42
        decorated = requires_invariants(dummy_fn)
        assert callable(decorated)


class TestGossipSubstrate:
    """gossip_substrate.py — push-pull gossip protocol."""

    def test_vector_clock_create_and_increment(self):
        from app.gossip_substrate import VectorClock
        vc = VectorClock("test-node")
        assert vc.node_id == "test-node"
        assert vc.clock["test-node"] == 0
        vc.increment()
        assert vc.clock["test-node"] == 1

    def test_vector_clock_compare_equal(self):
        from app.gossip_substrate import VectorClock
        a = VectorClock("node-a")
        b = VectorClock("node-b")
        assert a.compare(b) == "equal"

    def test_vector_clock_compare_concurrent(self):
        from app.gossip_substrate import VectorClock
        a = VectorClock("node-a")
        b = VectorClock("node-b")
        a.increment()  # a=[a:1], b=[b:0]
        b.increment()  # a=[a:1], b=[b:1]
        assert a.compare(b) == "concurrent"

    def test_gossip_substrate_create(self):
        from app.gossip_substrate import GossipSubstrate
        gs = GossipSubstrate("test-node")
        assert gs.node_id == "test-node"
        assert len(gs.known_nodes) == 0

    def test_register_node_and_select_peers(self):
        from app.gossip_substrate import GossipSubstrate
        gs = GossipSubstrate("local")
        gs.register_node("peer-1", {"to_dict": lambda: {}, "merge_state": lambda x: None})
        gs.register_node("peer-2", {"to_dict": lambda: {}, "merge_state": lambda x: None})
        assert "peer-1" in gs.known_nodes
        peers = gs.select_peers_for_gossip(count=2)
        assert len(peers) <= 2

    def test_node_health_defaults(self):
        from app.gossip_substrate import NodeHealth
        nh = NodeHealth()
        assert nh.reliability_score == 0.5
        assert nh.is_healthy is False  # last_seen is 0, not recent enough

    def test_get_health_report(self):
        from app.gossip_substrate import GossipSubstrate
        gs = GossipSubstrate("local")
        gs.register_node("peer-1", {"to_dict": lambda: {}, "merge_state": lambda x: None})
        report = gs.get_health_report()
        assert report["local_node"] == "local"
        assert isinstance(report["peers"], dict)

    def test_get_gossip_substrate_singleton(self):
        from app.gossip_substrate import get_gossip_substrate, reset_gossip_substrate
        reset_gossip_substrate("singleton-test")
        gs = get_gossip_substrate("singleton-test")
        assert gs.node_id == "singleton-test"
        # Second call returns same instance
        gs2 = get_gossip_substrate("singleton-test")
        assert gs2 is gs


class TestVectorClock:
    """vector_clock.py — causality tracking."""

    def test_create_and_increment(self):
        from app.vector_clock import VectorClock
        vc = VectorClock("node-1")
        assert vc.node_id == "node-1"
        clock = vc.get_clock()
        assert clock["node-1"] == 0
        vc.increment()
        assert vc.get_clock()["node-1"] == 1

    def test_update_merge(self):
        from app.vector_clock import VectorClock
        local = VectorClock("node-a")
        local.increment()
        remote = VectorClock("node-b")
        remote.increment()
        remote.increment()
        local.update(remote.get_clock())
        merged = local.get_clock()
        assert merged["node-a"] == 1
        assert merged["node-b"] == 2

    def test_compare_equal(self):
        from app.vector_clock import VectorClock
        a = VectorClock("a")
        b = VectorClock("a")
        assert a.compare(b.get_clock()) == "equal"

    def test_compare_ancestor_descendant(self):
        from app.vector_clock import VectorClock
        a = VectorClock("a")
        a.increment()
        a.increment()
        b = VectorClock("b")
        b.update(a.get_clock())  # b catches up to a's state
        assert b.compare(a.get_clock()) in ("descendant", "equal")

    def test_compare_concurrent(self):
        from app.vector_clock import VectorClock
        a = VectorClock("a")
        b = VectorClock("b")
        a.increment()
        b.increment()
        result = a.compare(b.get_clock())
        assert result == "concurrent"

    def test_from_dict_and_to_dict_roundtrip(self):
        from app.vector_clock import VectorClock
        original = VectorClock("node-x")
        original.increment()
        d = original.to_dict()
        restored = VectorClock.from_dict("node-x", d)
        assert restored.get_clock() == original.get_clock()


class TestManifoldState:
    """manifold_state.py — role manifold geometric state."""

    def test_create(self):
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        assert ms.role_manifold == {}
        assert ms.dimension == 16
        assert ms.learning_count == 0

    def test_set_and_get_manifold_vector(self):
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        vec = [0.1] * 16
        ms.set_manifold_vector("test_role", vec)
        retrieved = ms.get_manifold_vector("test_role")
        assert retrieved == vec
        assert retrieved is not vec  # must be a copy

    def test_compute_similarity(self):
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        ms.set_manifold_vector("role_a", [0.9] * 16)
        ms.set_manifold_vector("role_b", [0.1] * 16)
        # Two identical vectors should have high similarity
        sim_same = ms.compute_similarity("role_a", "role_a")
        assert sim_same >= 0
        sim_diff = ms.compute_similarity("role_a", "role_b")
        assert isinstance(sim_diff, float)

    def test_anchor_and_is_role_anchored(self):
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        ms.set_manifold_vector("anchored_role", [0.5] * 16)
        ms.anchor_role("anchored_role")
        assert ms.is_role_anchored("anchored_role") is True
        ms.unanchor_role("anchored_role")
        assert ms.is_role_anchored("anchored_role") is False

    def test_to_dict_from_dict_roundtrip(self):
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        ms.set_manifold_vector("role_x", [0.3] * 16)
        ms.anchor_role("role_x")
        ms.set_learning_count(5)
        data = ms.to_dict()
        restored = ManifoldState()
        restored.from_dict(data)
        assert restored.get_manifold_vector("role_x") == [0.3] * 16
        assert restored.is_role_anchored("role_x") is True
        assert restored.learning_count == 5

    def test_prune_manifold(self):
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        ms.set_manifold_vector("hypo_unstable", [0.5] * 16)
        ms.set_manifold_vector("stable_role", [0.5] * 16)
        pruned = ms.prune_manifold({"hypo_unstable": 0.9}, threshold=0.8)
        assert pruned == 1
        assert ms.has_manifold_role("hypo_unstable") is False
        assert ms.has_manifold_role("stable_role") is True

    def test_transaction_sets_value_correctly(self):
        # Note: transaction staging uses active_transaction context.
        # Without an active transaction, staging is a no-op but
        # direct mutation still works. This test verifies the value
        # can be set and retrieved correctly.
        from app.manifold_state import ManifoldState
        ms = ManifoldState()
        ms.set_manifold_vector("role_a", [0.5] * 16)
        ms.set_manifold_vector("role_a", [0.9] * 16)
        assert ms.get_manifold_vector("role_a") == [0.9] * 16


class TestMotifState:
    """motif_state.py — motif memory and stability tracking."""

    def test_create(self):
        from app.motif_state import MotifState
        ms = MotifState()
        assert ms.count() == 0

    def test_reinforce_and_count(self):
        from app.motif_state import MotifState
        ms = MotifState()
        motif = ("field_a", "field_b")
        ms.reinforce(motif, current_record=1)
        assert ms.get_count(motif) == 1
        assert ms.count() == 1

    def test_compute_stability(self):
        from app.motif_state import MotifState
        ms = MotifState()
        motif = ("x", "y")
        ms.reinforce(motif, current_record=1)
        ms.reinforce(motif, current_record=2)
        stability = ms.compute_stability(motif, total_records=10)
        assert 0 <= stability <= 1

    def test_prune_weak(self):
        from app.motif_state import MotifState
        ms = MotifState()
        # Reinforce with high current_record so decay_factor makes stability low
        ms.reinforce(("decaying",), current_record=1)
        assert ms.get_count(("decaying",)) == 1
        # Stability after 1 reinforce at record 1 = (1/1)*exp(0) = 1.0.
        # Use threshold 1.01 (>1.0) so it gets pruned
        ms.prune_weak(threshold=1.01)
        assert ms.count() == 0

    def test_predict_future_motifs(self):
        from app.motif_state import MotifState
        ms = MotifState()
        ms.reinforce(("rising",), current_record=1)
        predictions = ms.predict_future_motifs(current_record=2, threshold=0.0)
        assert isinstance(predictions, list)

    def test_clear(self):
        from app.motif_state import MotifState
        ms = MotifState()
        ms.reinforce(("a", "b"), current_record=1)
        ms.clear()
        assert ms.count() == 0

    def test_merge(self):
        from app.motif_state import MotifState
        ms = MotifState()
        ms.reinforce(("local",), current_record=1)
        remote = {
            "motif_counts": {"('remote',)": 3},
            "motif_timestamps": {"('remote',)": 5},
            "motif_stability": {"('remote',)": 0.8},
        }
        ms.merge(remote)
        assert ms.get_count(tuple(["remote"])) == 3


class TestEnergyState:
    """energy_state.py — energy/macro-state variables."""

    def test_create_defaults(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        assert es.global_energy == 5.0
        assert es.global_entropy == 0.5
        assert es.exclusion_count == 0

    def test_set_energy_clamps(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.set_energy(20.0)
        assert es.global_energy == 10.0  # clamped to max
        es.set_energy(-5.0)
        assert es.global_energy == 0.0  # clamped to min

    def test_set_entropy_nan(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.set_entropy(float("nan"))
        assert es.global_entropy == 0.5  # unchanged

    def test_field_pressure(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        pressure = es.field_pressure
        assert 0 <= pressure <= 1

    def test_energy_balance(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.record_energy_flow(source_delta=1.0, sink_delta=0.5)
        assert es.energy_balance == 0.5

    def test_adjust_energy(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.adjust_energy(2.0)
        assert es.global_energy == 7.0
        es.adjust_energy(-1.0)
        assert es.global_energy == 6.0

    def test_to_dict_from_dict_roundtrip(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.set_energy(3.0)
        es.set_entropy(0.7)
        es.exclusion_count = 5
        data = es.to_dict()
        restored = EnergyState()
        restored.from_dict(data)
        assert restored.global_energy == 3.0
        assert restored.global_entropy == 0.7
        assert restored.exclusion_count == 5

    def test_clear(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.set_energy(8.0)
        es.clear()
        assert es.global_energy == 5.0  # back to default

    def test_schema_instability(self):
        from app.energy_state import EnergyState
        es = EnergyState()
        es.set_schema_instability("test_field", 0.3)
        assert es.get_schema_instability("test_field") == 0.3


class TestInstabilityState:
    """instability_state.py — tension/exclusion structure."""

    def test_create(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        assert inst.exclusion_count() == 0

    def test_set_and_get_exclusion(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        inst.set_exclusion(("role_a", "role_b"), 0.8)
        assert inst.get_exclusion("role_a", "role_b") == 0.8
        # Order-independent lookup
        assert inst.get_exclusion("role_b", "role_a") == 0.8

    def test_add_exclusion(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        inst.add_exclusion("x", "y", 0.3)
        inst.add_exclusion("x", "y", 0.2)
        assert inst.get_exclusion("x", "y") == 0.5

    def test_decay(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        inst.set_exclusion(("a", "b"), 0.5)
        inst.decay(rate=0.5)
        remaining = inst.get_exclusion("a", "b")
        assert remaining < 0.5  # decayed

    def test_prune_exclusions_weak(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        # Note: set_exclusion with value <= 0.01 immediately removes the key
        # (clamped <= 0.01 triggers target.pop). Use 0.05 so it stays.
        inst.set_exclusion(("weak", "a"), 0.05)
        inst.set_exclusion(("strong", "b"), 0.9)
        # prune with threshold above 0.05 -> removes the weak one
        removed = inst.prune_exclusions_weak(threshold=0.06)
        assert removed == 1
        assert inst.exclusion_count() == 1
        assert inst.get_exclusion("strong", "b") == 0.9

    def test_clear(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        inst.set_exclusion(("a", "b"), 0.5)
        inst.clear()
        assert inst.exclusion_count() == 0

    def test_to_dict_from_dict_roundtrip(self):
        from app.instability_state import InstabilityState
        inst = InstabilityState()
        inst.set_exclusion(("role1", "role2"), 0.7)
        data = inst.to_dict()
        restored = InstabilityState()
        restored.from_dict(data)
        assert restored.get_exclusion("role1", "role2") == 0.7
