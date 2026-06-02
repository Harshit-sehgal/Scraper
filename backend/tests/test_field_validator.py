"""Test runtime field validation."""

from app.field_validator import validate_world_state
from app.semantic_persistence import clear_semantic_state
from app.semantic_world_state import get_world_state


def test_fresh_state_is_valid():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    issues = validate_world_state(ws)
    assert not issues, f"Fresh state should be clean: {issues}"


def test_nan_energy_detected():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._energy._global_energy = float("nan")  # Bypass setter
    issues = validate_world_state(ws)
    assert any("NaN" in i for i in issues)


def test_nan_entropy_detected():
    """global_entropy NaN should be flagged."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._energy._global_entropy = float("nan")
    issues = validate_world_state(ws)
    assert any("entropy" in i.lower() and "nan" in i.lower() for i in issues)


def test_inf_energy_detected():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._energy._global_energy = float("inf")
    issues = validate_world_state(ws)
    assert any("inf" in i for i in issues)


def test_orphan_region_detected():
    """A region with no competing_roles should be flagged as orphan."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    from app.core_types import FieldConflictRegion

    orphan = FieldConflictRegion(competing_roles=[], token="orphan", instability=0.5)
    ws._topology.append_region(orphan)
    issues = validate_world_state(ws)
    assert any("orphan" in i.lower() for i in issues)


def test_nan_region_instability_detected():
    """Bypass topology clamping by hacking the internal FieldConflictRegion."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    from app.core_types import FieldConflictRegion

    # append_region clamps NaN, so we hack the internal object afterwards
    bad = FieldConflictRegion(competing_roles=["a"], token="bad", instability=0.5)
    ws._topology.append_region(bad)
    regions = ws._topology._get_regions()
    object.__setattr__(regions[-1], "instability", float("nan"))
    issues = validate_world_state(ws)
    assert any("nan" in i and "instability" in i.lower() for i in issues)


def test_instability_out_of_bounds():
    """Bypass topology clamping by hacking the internal FieldConflictRegion."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    from app.core_types import FieldConflictRegion

    bad = FieldConflictRegion(competing_roles=["a"], token="bad", instability=0.5)
    ws._topology.append_region(bad)
    regions = ws._topology._get_regions()
    object.__setattr__(regions[-1], "instability", 1.5)
    issues = validate_world_state(ws)
    assert any("out of bounds" in i and "instability" in i.lower() for i in issues)


def test_energy_out_of_bounds():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    from app.core_types import FieldConflictRegion

    bad = FieldConflictRegion(competing_roles=["a"], token="bad", instability=0.5, local_energy=20.0)
    ws._topology.append_region(bad)
    issues = validate_world_state(ws)
    assert any("out of bounds" in i and "energy" in i.lower() for i in issues)


def test_exclusion_out_of_bounds():
    """Directly hack the internal instability exclusions dict."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._instability._exclusions[("test", "check")] = 2.5
    issues = validate_world_state(ws)
    assert any("exclusion" in i.lower() and "out of bounds" in i for i in issues)


def test_entropy_metric_out_of_bounds():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._energy._global_entropy = 5.0
    issues = validate_world_state(ws)
    assert any("entropy" in i.lower() and "out of bounds" in i for i in issues)


def test_integrity_out_of_bounds():
    """Bypass topology clamping by hacking the internal FieldConflictRegion."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    from app.core_types import FieldConflictRegion

    bad = FieldConflictRegion(competing_roles=["a"], token="bad", instability=0.5, integrity=0.5)
    ws._topology.append_region(bad)
    regions = ws._topology._get_regions()
    object.__setattr__(regions[-1], "integrity", 2.0)
    issues = validate_world_state(ws)
    assert any("integrity" in i.lower() and "out of bounds" in i for i in issues)


def test_energy_global_out_of_bounds():
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._energy._global_energy = 50.0
    issues = validate_world_state(ws)
    assert any("global_energy" in i and "out of bounds" in i for i in issues)


def test_decision_history_exceeds_5000():
    """decision_history > 5000 entries should be flagged as memory bloat."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    ws._history.decision_history = [{"placeholder": i} for i in range(5001)]
    issues = validate_world_state(ws)
    assert any("decision_history" in i and "5000" in i for i in issues)


def test_region_count_exceeds_500():
    """field_regions > 500 should be flagged as memory bloat."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    from app.core_types import FieldConflictRegion

    # Bypass topology clamping and MVCC by hacking _regions directly
    ws._topology._regions = [
        FieldConflictRegion(competing_roles=["a"], token=f"tok{i}", instability=0.5, integrity=0.5) for i in range(501)
    ]
    issues = validate_world_state(ws)
    assert any("field_regions" in i and "500" in i for i in issues)


def test_learned_exclusions_exceeds_500():
    """learned_exclusions > 500 entries should be flagged as memory bloat."""
    clear_semantic_state(clear_file=False)
    ws = get_world_state()
    # Add 529 entries (23×23 grid) to exceed 500 threshold
    ws._instability._exclusions = {(f"r{i}", f"r{j}"): 0.5 for i in range(23) for j in range(23)}
    assert len(ws._instability.exclusions) > 500  # Sanity check: 529
    issues = validate_world_state(ws)
    assert any("learned_exclusions" in i and "500" in i for i in issues)
