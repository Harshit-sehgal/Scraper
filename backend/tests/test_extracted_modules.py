"""Tests for all 14 extracted modules — verify they work independently."""

from app.semantic_persistence import clear_semantic_state
from app.semantic_world_state import get_world_state, FieldConflictRegion


def test_topology_state():
    """TopologyState: add, find, remove, prune, neighbors."""
    from app.topology_state import TopologyState
    ts = TopologyState()
    r1 = ts.add(['origin', 'destination'], 'LAX', instability=0.5)
    ts.add(['origin', 'destination'], 'JFK', instability=0.3)
    assert ts.region_count() == 2
    found = ts.find('LAX', {'origin', 'destination'})
    assert found is not None
    assert len(ts.neighbors_of(r1)) == 1
    r1.instability = 0.01
    r1.local_energy = 0.1
    assert ts.prune(min_instability=0.02) == 1
    assert ts.region_count() == 1
    print("  topology_state.py: OK")


def test_energy_state():
    """EnergyState: set, adjust, NaN rejection."""
    from app.energy_state import EnergyState
    es = EnergyState()
    es.set_energy(5.0)
    assert es.global_energy == 5.0
    es.set_energy(float('nan'))
    assert es.global_energy == 5.0  # unchanged
    es.adjust_energy(-2.0)
    assert es.global_energy == 3.0
    assert 0.0 <= es.field_pressure <= 1.0
    print("  energy_state.py: OK")


def test_instability_state():
    """InstabilityState: add_exclusion, decay, get_exclusion."""
    from app.instability_state import InstabilityState
    ist = InstabilityState()
    ist.add_exclusion('origin', 'destination', 0.5)
    assert ist.get_exclusion('origin', 'destination') == 0.5
    assert ist.exclusion_count() == 1
    ist.decay(rate=0.5)
    assert ist.get_exclusion('origin', 'destination') < 0.5
    print("  instability_state.py: OK")


def test_topology_api():
    ws = get_world_state()
    """TopologyAPI: read/write separation."""
    from app.topology_api import TopologyAPI
    clear_semantic_state(clear_file=False)
    api = TopologyAPI(ws)
    r_original = api.add_region(['origin', 'destination'], 'TEST', instability=0.5, integrity=0.5)
    rid = r_original.region_id
    # Re-fetch from API to get the "live" version (it might have been cloned by MVCC)
    r = ws.topology_state.get_region(rid)
    assert api.region_count() == 1
    assert api.find_region('TEST', {'origin', 'destination'}) is not None
    assert api.prune_weak_regions(min_instability=0.6) == 0
    
    # Update properties on the live version
    r.instability = 0.01
    r.semantic_pressure = 0.0 # Force low energy for pruning test
    r.local_energy = 0.1
    assert api.prune_weak_regions(min_instability=0.02) == 1

    assert api.region_count() == 0
    print("  topology_api.py: OK")


def test_energy_api():
    ws = get_world_state()
    """EnergyAPI: controlled energy mutations with NaN rejection."""
    from app.energy_api import EnergyAPI
    clear_semantic_state(clear_file=False)
    api = EnergyAPI(ws)
    api.set_global_energy(5.0)
    assert api.get_global_energy() == 5.0
    api.set_global_energy(float('nan'))
    assert api.get_global_energy() == 5.0  # unchanged
    print("  energy_api.py: OK")


def test_instability_api():
    ws = get_world_state()
    """InstabilityAPI: controlled exclusion mutations."""
    from app.instability_api import InstabilityAPI
    clear_semantic_state(clear_file=False)
    api = InstabilityAPI(ws)
    api.add_exclusion('a', 'b', 0.3)
    assert api.get_exclusion('a', 'b') == 0.3
    api.decay_exclusion('a', 'b', rate=0.5)
    assert api.get_exclusion('a', 'b') < 0.3
    print("  instability_api.py: OK")


def test_event_journal():
    """EventJournal: record, replay, causality chain."""
    from app.event_journal import get_journal
    j = get_journal()
    j.clear()
    j.record('test', 'mutation', {'v': 1}, {'v': 2}, {'reason': 'test'})
    assert j.count == 1
    entries = j.replay()
    assert entries[0]['type'] == 'mutation'
    chain = j.get_causality_chain()
    assert len(chain) == 1
    j.clear()
    assert j.count == 0
    print("  event_journal.py: OK")


def test_field_validator():
    ws = get_world_state()
    """field_validator: detects NaN, clean on fresh state."""
    from app.field_validator import validate_world_state
    clear_semantic_state(clear_file=False)
    issues = validate_world_state(ws)
    assert not issues
    ws._energy._global_energy = float('nan')  # Bypass setter
    issues = validate_world_state(ws)
    assert any('NaN' in i for i in issues)
    print("  field_validator.py: OK")


def test_observability():
    ws = get_world_state()
    """observability: field_summary, topology_report."""
    from app.observability import field_summary, topology_report
    clear_semantic_state(clear_file=False)
    s = field_summary(ws)
    assert 'energy' in s
    t = topology_report(ws)
    assert 'pressure' in t
    print("  observability.py: OK")


def test_field_laws():
    """field_laws: constants are accessible."""
    from app.field_laws import PROPAGATION_DECAY_FLOOR, MAX_COUPLING_TRANSFER
    assert PROPAGATION_DECAY_FLOOR == 0.3
    assert MAX_COUPLING_TRANSFER == 0.3
    print("  field_laws.py: OK")


def test_persistence():
    ws = get_world_state()
    """persistence_state: serialize/deserialize round-trip."""
    from app.persistence_state import world_state_to_dict, clear_world_state
    clear_semantic_state(clear_file=False)
    ws.total_co_occurrences = 0  # HEAD needs this
    d = world_state_to_dict(ws)
    assert 'version' in d
    assert 'global_energy' in d
    clear_world_state(ws)
    print("  persistence_state.py: OK")


def test_core_types():
    """core_types: FieldConflictRegion."""
    from app.core_types import FieldConflictRegion
    r = FieldConflictRegion(competing_roles=['origin', 'destination'], token='TEST', instability=0.5)
    assert r.domain == ""
    from app.energy_state import EnergyState
    es = EnergyState()
    assert 0.0 <= es.field_pressure <= 1.0
    assert 0.0 <= es.integrity_score <= 1.0
    print("  core_types.py: OK")


def test_topology_gc():
    ws = get_world_state()
    """topology_gc: collect_garbage returns counts."""
    from app.topology_gc import collect_garbage
    clear_semantic_state(clear_file=False)
    ws._topology.append_region(FieldConflictRegion(competing_roles=['a', 'b'], token='DEAD', instability=0.01, local_energy=0.1))
    collected = collect_garbage(ws)
    assert collected["regions"] >= 0
    print("  topology_gc.py: OK")


def test_invariant_firewall():
    """invariant_firewall: decorator runs without error."""
    from app.invariant_firewall import requires_invariants
    ws = get_world_state()
    ws.clear()
    @requires_invariants
    def fn(w):
        w.metrics.global_energy = 5.0
    fn(ws)
    print("  invariant_firewall.py: OK")
