"""Tests for the 10 kept extracted modules — verify they work independently."""

from app.semantic_persistence import clear_semantic_state
from app.semantic_world_state import get_world_state


def test_topology_state() -> None:
    """TopologyState: add, find, remove, prune, neighbors."""
    from app.topology_state import TopologyState

    ts = TopologyState()
    r1 = ts.add(["origin", "destination"], "LAX", instability=0.5)
    ts.add(["origin", "destination"], "JFK", instability=0.3)
    assert ts.region_count() == 2
    found = ts.find("LAX", {"origin", "destination"})
    assert found is not None
    assert len(ts.neighbors_of(r1)) == 1
    r1.instability = 0.01
    r1.local_energy = 0.1
    assert ts.prune(min_instability=0.02) == 1
    assert ts.region_count() == 1


def test_energy_state() -> None:
    """EnergyState: set, adjust, NaN rejection."""
    from app.energy_state import EnergyState

    es = EnergyState()
    es.set_energy(5.0)
    assert es.global_energy == 5.0
    es.set_energy(float("nan"))
    assert es.global_energy == 5.0  # unchanged
    es.adjust_energy(-2.0)
    assert es.global_energy == 3.0
    assert 0.0 <= es.field_pressure <= 1.0


def test_instability_state() -> None:
    """InstabilityState: add_exclusion, decay, get_exclusion."""
    from app.instability_state import InstabilityState

    ist = InstabilityState()
    ist.add_exclusion("origin", "destination", 0.5)
    assert ist.get_exclusion("origin", "destination") == 0.5
    assert ist.exclusion_count() == 1
    ist.decay(rate=0.5)
    assert ist.get_exclusion("origin", "destination") < 0.5


def test_instability_api() -> None:
    ws = get_world_state()
    """InstabilityAPI: controlled exclusion mutations."""
    from app.instability_api import InstabilityAPI

    clear_semantic_state(clear_file=False)
    api = InstabilityAPI(ws)
    api.add_exclusion("a", "b", 0.3)
    assert api.get_exclusion("a", "b") == 0.3
    api.decay_exclusion("a", "b", rate=0.5)
    assert api.get_exclusion("a", "b") < 0.3


def test_event_journal() -> None:
    """EventJournal: record, replay, causality chain."""
    from app.event_journal import get_journal

    j = get_journal()
    j.clear()
    j.record("test", "mutation", {"v": 1}, {"v": 2}, {"reason": "test"})
    assert j.count == 1
    entries = j.replay()
    assert entries[0]["type"] == "mutation"
    chain = j.get_causality_chain()
    assert len(chain) == 1
    j.clear()
    assert j.count == 0


def test_field_validator() -> None:
    ws = get_world_state()
    """field_validator: detects NaN, clean on fresh state."""
    from app.field_validator import validate_world_state

    clear_semantic_state(clear_file=False)
    issues = validate_world_state(ws)
    assert not issues
    ws._energy._global_energy = float("nan")  # Bypass setter
    issues = validate_world_state(ws)
    assert any("NaN" in i for i in issues)


def test_observability() -> None:
    ws = get_world_state()
    """observability: field_summary, topology_report."""
    from app.observability import field_summary, topology_report

    clear_semantic_state(clear_file=False)
    s = field_summary(ws)
    assert "energy" in s
    t = topology_report(ws)
    assert "pressure" in t


def test_field_laws() -> None:
    """field_laws: constants are accessible."""
    from app.field_laws import MAX_COUPLING_TRANSFER, PROPAGATION_DECAY_FLOOR

    assert PROPAGATION_DECAY_FLOOR == 0.3
    assert MAX_COUPLING_TRANSFER == 0.3


def test_core_types() -> None:
    """core_types: FieldConflictRegion."""
    from app.core_types import FieldConflictRegion

    r = FieldConflictRegion(competing_roles=["origin", "destination"], token="TEST", instability=0.5)
    assert r.domain == ""
    from app.energy_state import EnergyState

    es = EnergyState()
    assert 0.0 <= es.field_pressure <= 1.0
    assert 0.0 <= es.integrity_score <= 1.0


def test_invariant_firewall() -> None:
    """invariant_firewall: decorator runs without error."""
    from app.invariant_firewall import requires_invariants

    ws = get_world_state()
    ws.clear()

    @requires_invariants
    def fn(w) -> None:
        w.metrics.global_energy = 5.0

    fn(ws)
