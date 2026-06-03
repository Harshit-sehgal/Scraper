from app.semantic_os import get_semantic_os
from app.semantic_world_state import get_world_state


def test_telemetry_emission() -> None:
    sos = get_semantic_os()
    sos.ws.clear()

    # 1. Emit some telemetry
    sos.log_manual_telemetry("test_event", {"foo": "bar", "region_id": "r1"})

    # 2. Query telemetry
    stream = sos.get_telemetry()
    # Now 2 events: 'test_event' AND the automatic 'transaction' event
    assert len(stream) == 2
    assert any(t["type"] == "test_event" and t["details"]["foo"] == "bar" for t in stream)
    assert any(t["type"] == "transaction" for t in stream)

    # 3. Verify heatmap pulse
    heatmap = sos.get_activity_heatmap()
    assert heatmap["r1"] == 1.0


def test_heatmap_decay() -> None:
    ws = get_world_state()
    ws.clear()

    with ws.transaction("pulse"):
        ws._observability.pulse_heatmap("r1", 1.0)

    assert ws._observability.heatmap["r1"] == 1.0

    # Decay
    with ws.transaction("decay"):
        ws._observability.decay_heatmap(rate=0.5)

    assert ws._observability.heatmap["r1"] == 0.5


def test_drift_logging() -> None:
    ws = get_world_state()
    ws.clear()

    with ws.transaction("drift"):
        ws._observability.log_drift("role_a", 0.05)
        ws._observability.log_drift("role_a", 0.02)

    drift = ws._observability.get_role_drift("role_a")
    assert drift == [0.05, 0.02]


def test_observability_persistence() -> None:
    ws = get_world_state()
    ws.clear()

    with ws.transaction("setup"):
        ws._observability.pulse_heatmap("r1", 5.0)
        ws._observability.log_drift("role_a", 0.1)

    state = ws.to_dict()
    ws.clear()

    ws.from_dict(state)
    assert ws._observability.heatmap["r1"] == 5.0
    assert ws._observability.get_role_drift("role_a") == [0.1]


def test_manifold_drift_telemetry() -> None:
    ws = get_world_state()
    ws.clear()

    # 1. Setup role
    ws._manifold.set_manifold_vector("drifting_role", [0.5] * 16)

    # 2. Mock RoleEmbeddingEngine.relax_manifold to simulate drift
    from unittest.mock import patch

    def mock_relax(self):
        # Manually mutate the manifold in the world state
        vec = self.ws._manifold.get_manifold_vector("drifting_role")
        vec[0] += 0.1
        self.ws._manifold.set_manifold_vector("drifting_role", vec)

    with patch("app.semantic_inference_engine.RoleEmbeddingEngine.relax_manifold", mock_relax):
        ws.relax_topology()

    # 3. Verify drift logged
    drift = ws._observability.get_role_drift("drifting_role")
    assert len(drift) > 0
    assert drift[0] > 0.0

    # 4. Verify telemetry emitted
    telemetry = ws._observability.telemetry
    assert any(t["type"] == "manifold_relaxation" for t in telemetry)


def test_health_guardian_alert() -> None:
    ws = get_world_state()
    ws.clear()

    # 1. Setup critical energy
    ws._energy.set_energy(9.0)

    # 2. Evolve macro state to trigger check
    ws.evolve_macro_state()

    # 3. Verify alert emitted
    telemetry = ws._observability.telemetry
    assert any(t["type"] == "health_alert" and t["details"]["reason"] == "critical_energy" for t in telemetry)
