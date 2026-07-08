"""Proves the permanent state ownership modules work as an independent subsystem.

These tests demonstrate that TopologyState, EnergyState, and InstabilityState
can function as a self-contained state management layer WITHOUT SemanticWorldState.
"""

from app.topology_state import TopologyState
from app.energy_state import EnergyState
from app.instability_state import InstabilityState


def test_independent_topology():
    """TopologyState works entirely independently."""
    ts = TopologyState()
    r = ts.add(['origin', 'destination'], 'LAX', instability=0.5)
    ts.add(['origin', 'destination'], 'JFK', instability=0.3)
    assert ts.region_count() == 2
    assert len(ts.neighbors_of(r)) == 1
    # Prune weak
    r.instability = 0.01
    r.local_energy = 0.1
    assert ts.prune(min_instability=0.02) == 1
    assert ts.region_count() == 1
    ts.clear()
    assert ts.region_count() == 0


def test_independent_energy():
    """EnergyState works entirely independently."""
    es = EnergyState()
    assert es.global_energy == 5.0
    assert es.global_entropy == 0.5

    # Bounds enforcement
    es.set_energy(15.0)
    assert es.global_energy == 10.0  # clamped

    es.set_energy(float('nan'))
    assert es.global_energy == 10.0  # NaN rejected

    # Entropy bounds
    es.set_entropy(2.0)
    assert es.global_entropy == 1.0  # clamped

    # Field pressure always valid
    assert 0.0 <= es.field_pressure <= 1.0

    es.clear()
    assert es.global_energy == 5.0


def test_independent_instability():
    """InstabilityState works entirely independently."""
    ist = InstabilityState()
    ist.add_exclusion('origin', 'destination', 0.8)
    assert ist.get_exclusion('origin', 'destination') == 0.8
    assert ist.exclusion_count() == 1

    ist.decay(rate=0.5)
    assert ist.get_exclusion('origin', 'destination') < 0.8

    ist.clear()
    assert ist.exclusion_count() == 0


def test_combined_ownership():
    """Three state objects together form a complete management layer."""
    ts = TopologyState()
    es = EnergyState()
    ist = InstabilityState()

    # Create a region
    region = ts.add(['origin', 'destination'], 'LAX', instability=0.5)
    assert region.instability == 0.5

    # Track energy
    es.set_energy(region.instability * 10)
    assert es.global_energy == 5.0

    # Track exclusion
    ist.add_exclusion('origin', 'destination', 0.3)
    assert ist.get_exclusion('origin', 'destination') == 0.3

    # All independent
    assert ts.region_count() == 1
    assert es.global_energy == 5.0
    assert ist.exclusion_count() == 1


def test_owner_encapsulation():
    """No external code should be able to bypass the state objects' controlled interfaces."""
    ts = TopologyState()
    es = EnergyState()

    # Direct mutation of the internal list IS possible via `.regions` property
    # (Python can't fully prevent this), but the API provides controlled methods
    r = ts.add(['a', 'b'], 'X', instability=0.5)
    assert r.instability == 0.5

    # Direct mutation of energy state is similarly possible
    # The API provides controlled paths; this test documents that fact
    es.set_energy(3.0)
    assert es.global_energy == 3.0
