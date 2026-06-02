from app.instability_api import get_immune_system
from app.semantic_world_state import get_world_state


def test_source_quarantine():
    ws = get_world_state()
    ws.clear()
    _ = get_immune_system(ws=ws)

    source = "malicious-site.com"

    # 1. Perturb from unknown source (allowed)
    ws.observe_field_perturbation({"source_url": source, "_allocation_conflicts": [{"role": "r1", "candidate": "t1"}]}, [])

    # Verify exclusion was updated
    # ... Wait, observe_field_perturbation updates exclusions based on ROLE_EXCLUSIVITY


def test_shielding_high_integrity_roles():
    ws = get_world_state()
    ws.clear()
    immune = get_immune_system(ws=ws)

    # 1. Setup a high-integrity role (Envelope)
    ws._abstraction.create_envelope("env1", ["r1"], [0.5] * 16)

    # 2. Setup High Energy (Fever state)
    ws._energy.set_energy(9.0)

    # 3. Attempt perturbation targeting that role
    # Should be shielded
    allowed = immune.validate_perturbation("site.com", "tok", ["env1"])
    assert allowed is False


def test_quarantine_block():
    ws = get_world_state()
    ws.clear()
    immune = get_immune_system(ws=ws)

    source = "bad-source"
    immune.quarantine_source(source, penalty=0.9)  # trust -> 0.1

    # Perturbation should be blocked
    allowed = immune.validate_perturbation(source, "tok", ["r1"])
    assert allowed is False


def test_adversarial_pressure_quarantine():
    ws = get_world_state()
    ws.clear()
    immune = get_immune_system(ws=ws)

    source = "shady-site.com"
    # Pre-lower trust a bit
    immune.quarantine_source(source, penalty=0.5)  # trust -> 0.5

    # 1. Setup High Energy (System is stressed)
    ws._energy.set_energy(6.0)

    # 2. Attempt perturbation - should trigger further quarantine
    allowed = immune.validate_perturbation(source, "tok", ["r1"])
    assert allowed is False
    assert immune.get_trust(source) == 0.3  # 0.5 - 0.2


def test_immune_response_cascade():
    ws = get_world_state()
    ws.clear()

    # 1. Setup an anchored role and corrupt it (move far from baseline)
    role = "price"
    ws._manifold.set_manifold_vector(role, [0.0] * 16)  # Far from PRICE type vector
    ws._manifold.anchor_role(role)
    ws._energy.set_schema_instability(role, 0.9)  # High instability

    # 2. Trigger macro evolution
    ws.evolve_macro_state()

    # 3. Verify recovery
    vec = ws._manifold.get_manifold_vector(role)
    # Price type vector has 1.0 at index 0
    assert vec[0] > 0.5
    assert ws.metrics.schema_instability[role] == 0.5

    # Verify telemetry
    telemetry = ws._observability.telemetry
    assert any(t["type"] == "immune_recovery" for t in telemetry)
