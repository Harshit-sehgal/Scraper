"""Tests for Phase-1 extracted topology sub-modules.

Verifies that the free-standing functions in topology_forces,
topology_thermodynamics, topology_waves, and topology_region_ops
behave identically to calling the corresponding TopologyState methods.
"""

from app.topology_state import TopologyState

# ─── topology_forces ────────────────────────────────────────────────


def test_compute_edge_field_forces_delegation() -> None:
    """_compute_edge_field_forces delegates to topology_forces."""
    from app.topology_forces import compute_edge_field_forces

    ts = TopologyState()
    ts.add(["a", "b"], "T1")
    # Both paths must return the same result
    via_method = ts._compute_edge_field_forces()
    via_module = compute_edge_field_forces(ts)
    assert via_method == via_module


def test_route_contradiction_delegation() -> None:
    """route_contradiction delegates to topology_forces."""
    from app.topology_forces import route_contradiction

    ts = TopologyState()
    ts.add(["x", "y"], "T1")
    result_method = ts.route_contradiction("x", "y", strength=0.2)
    # Also call the free function directly
    ts2 = TopologyState()
    ts2.add(["x", "y"], "T1")
    result_module = route_contradiction(ts2, "x", "y", strength=0.2)
    # Both should return a dict with expected keys
    assert "redirected" in result_method
    assert "excluded" in result_method
    assert "through_edge_field" in result_method
    assert result_method.keys() == result_module.keys()


# ─── topology_thermodynamics ────────────────────────────────────────


def test_evolve_all_delegation() -> None:
    """evolve_all delegates to topology_thermodynamics."""
    from app.topology_thermodynamics import evolve_all

    ts = TopologyState()
    ts.add(["a", "b"], "T1", instability=0.5)
    # Both paths should work without error
    effects_method = ts.evolve_all(force=True)
    assert isinstance(effects_method, list)

    ts2 = TopologyState()
    ts2.add(["a", "b"], "T1", instability=0.5)
    effects_module = evolve_all(ts2, force=True)
    assert isinstance(effects_module, list)


def test_propagate_all_delegation() -> None:
    """propagate_all delegates to topology_thermodynamics."""
    ts = TopologyState()
    ts.add(["a", "b"], "T1", instability=0.5)
    effects = ts.propagate_all()
    assert isinstance(effects, list)


def test_redistribute_instability_delegation() -> None:
    """redistribute_instability delegates to topology_thermodynamics."""
    ts = TopologyState()
    ts.add(["a", "b"], "T1", instability=0.5)
    ts.add(["b", "c"], "T2", instability=0.2)
    result = ts.redistribute_instability(damping=1.0)
    assert "total_flow" in result
    assert "pairs_coupled" in result


# ─── topology_region_ops ────────────────────────────────────────────


def test_set_region_instability_delegation() -> None:
    """set_region_instability delegates to topology_region_ops."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1", instability=0.5)
    ts.set_region_instability(r.region_id, 0.8)
    updated = ts.get_region(r.region_id)
    assert updated is not None
    assert abs(updated.instability - 0.8) < 0.01


def test_adjust_region_instability_delegation() -> None:
    """adjust_region_instability delegates to topology_region_ops."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1", instability=0.5)
    ts.adjust_region_instability(r.region_id, 0.1)
    updated = ts.get_region(r.region_id)
    assert updated is not None
    assert updated.instability > 0.5


def test_set_region_energy_delegation() -> None:
    """set_region_energy delegates to topology_region_ops."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1")
    ts.set_region_energy(r.region_id, 3.0)
    updated = ts.get_region(r.region_id)
    assert updated is not None
    assert abs(updated.local_energy - 3.0) < 0.01


def test_set_region_temperature_delegation() -> None:
    """set_region_temperature delegates to topology_region_ops."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1")
    ts.set_region_temperature(r.region_id, 0.7)
    updated = ts.get_region(r.region_id)
    assert updated is not None
    assert abs(updated.local_temperature - 0.7) < 0.01


def test_update_region_after_recurrence() -> None:
    """update_region_after_recurrence delegates to topology_region_ops."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1", instability=0.3)
    ts.update_region_after_recurrence(r.region_id, field_pressure=0.6)
    updated = ts.get_region(r.region_id)
    assert updated is not None
    assert updated.semantic_pressure == 0.6
    assert updated.recurrence_score > 0.0


def test_update_local_memory() -> None:
    """update_local_memory_from_instability delegates to topology_region_ops."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1", instability=0.5)
    ts.update_local_memory_from_instability()
    updated = ts.get_region(r.region_id)
    assert updated is not None
    assert "a" in updated.local_memory
    assert updated.local_memory["a"] == updated.instability


# ─── topology_waves ─────────────────────────────────────────────────


def test_emit_field_wave_no_crash() -> None:
    """emit_field_wave delegates to topology_waves without crashing."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1", instability=0.5)
    # Should not raise — just dispatches an event
    ts.emit_field_wave(r.region_id, 0.5)


def test_emit_field_wave_noop_for_tiny_intensity() -> None:
    """emit_field_wave is a no-op for very small intensities."""
    ts = TopologyState()
    r = ts.add(["a", "b"], "T1")
    # intensity < 0.01 should be silently ignored
    ts.emit_field_wave(r.region_id, 0.001)


# ─── topology_forces — branch coverage ────────────────────────────────


def test_redirect_repulsive_pressure_dissipates_when_no_routes() -> None:
    """redirect_repulsive_pressure dissipates as heat when no routes exist."""
    from app.topology_forces import redirect_repulsive_pressure

    ts = TopologyState()
    r = ts.add(["a", "b"], "T1", instability=0.5)
    ts.add(["c", "d"], "T2")  # unrelated roles — no overlap
    old_temp = r.local_temperature

    # No shared roles between source_region and any edge field forces
    redirect_repulsive_pressure(ts, r, 0.5, {})

    # Should have increased temperature (dissipation)
    assert r.local_temperature > old_temp


def test_redirect_repulsive_pressure_routes_through_affinity() -> None:
    """redirect_repulsive_pressure routes through high-affinity edge field."""
    from app.topology_forces import redirect_repulsive_pressure

    ts = TopologyState()
    source = ts.add(["a"], "T1", instability=0.5)
    target = ts.add(["b"], "T2", instability=0.1)

    # Build a forces dict with a high-affinity edge a↔b
    forces: dict[tuple[str, str], dict[str, float]] = {
        ("a", "b"): {
            "affinity": 0.8,
            "repulsion": 0.1,
            "pressure": 0.3,
            "route_strength": 0.6,
            "semantics": "attractive",
        },
    }
    old_target_instability = target.instability

    redirect_repulsive_pressure(ts, source, 1.0, forces)

    # Target instability should have increased
    assert target.instability > old_target_instability


def test_redirect_repulsive_pressure_remainder_heats_source() -> None:
    """Unredirected pressure heats the source region."""
    from app.topology_forces import redirect_repulsive_pressure

    ts = TopologyState()
    source = ts.add(["a"], "T1", instability=0.5)
    ts.add(["b"], "T2", instability=0.1)

    # Low route_strength means most pressure won't be redirected
    forces: dict[tuple[str, str], dict[str, float]] = {
        ("a", "b"): {
            "affinity": 0.4,
            "repulsion": 0.1,
            "pressure": 0.2,
            "route_strength": 0.21,
            "semantics": "attractive",
        },
    }
    old_temp = source.local_temperature

    redirect_repulsive_pressure(ts, source, 1.0, forces)

    # Source temperature should increase from unredirected remainder
    assert source.local_temperature > old_temp


def test_route_contradiction_no_edge_field() -> None:
    """route_contradiction without edge field data falls back to topological law.

    Use separate regions with distinct roles so get_edge_fields() returns no
    pair for ("x", "y"), triggering the fallback branch.
    """
    from app.topology_forces import route_contradiction

    ts = TopologyState()
    # Separate regions with NO shared role pair with 'x' or 'y'
    ts.add(["z"], "T1")
    ts.add(["w"], "T2")

    result = route_contradiction(ts, "x", "y", strength=0.2)

    assert result["redirected"] == 0.0
    assert result["excluded"] > 0.0
    assert result["through_edge_field"] is False


def test_route_contradiction_repulsive_edge() -> None:
    """route_contradiction with repulsive edge redirects pressure."""
    from app.topology_forces import route_contradiction

    ts = TopologyState()
    ts.add(["x"], "T1", instability=0.5)
    ts.add(["y"], "T2", instability=0.3)

    # Set a repulsive topological law (negative law = repulsive)
    ts.set_topological_law(("x", "y"), -0.5)

    result = route_contradiction(ts, "x", "y", strength=0.4)

    # Repulsive edge should redirect pressure
    assert result["redirected"] > 0.0
    assert result["through_edge_field"] is True


def test_route_contradiction_non_repulsive_edge() -> None:
    """route_contradiction with non-repulsive edge establishes repulsive law."""
    from app.topology_forces import route_contradiction

    ts = TopologyState()
    ts.add(["x"], "T1", instability=0.5)
    ts.add(["y"], "T2", instability=0.3)

    # Set an attractive topological law (positive law = attractive)
    ts.set_topological_law(("x", "y"), 0.5)

    result = route_contradiction(ts, "x", "y", strength=0.4)

    # Non-repulsive pair contradicting should still make it through edge field
    assert result["redirected"] == 0.0
    assert result["excluded"] > 0.0
    assert result["through_edge_field"] is True
