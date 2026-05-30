from app.semantic_world_state import get_world_state
from app.semantic_os import get_semantic_os


def test_autonomous_action_dispatch():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()

    # 1. Register an action at a specific manifold point
    # Point [1.0, 0, 0, ...] represents a 'Price' goal
    action_point = [0.5] * 16
    action_point[0] = 1.0
    sos.register_action("verify_price", action_point, "price_verifier_plugin", threshold=0.4)

    # 2. Setup a stable basin near that point
    # Use highly differentiated vector [1, 0, 1, 0...] for high internal variance (certainty)
    action_point = [1.0, 0.0] * 8
    ws._manifold.set_manifold_vector("cost", action_point)
    sos.register_action("verify_price", action_point, "price_verifier_plugin", threshold=0.4)

    ws._topology.add(["cost"], "500", instability=0.1)  # stable

    # 3. Trigger dispatch
    triggered = sos.trigger_actions()

    # 4. Verify verification action was triggered
    assert triggered == 1
    history = ws._action.action_history
    assert len(history) == 1
    assert history[0]["action_id"] == "verify_price"
    assert history[0]["details"]["role"] == "cost"


def test_outcome_feedback_loop():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()

    # 1. Action anchor
    target = [0.0] * 16
    sos.register_action("audit", target, "auditor", threshold=0.5)

    # 2. Role at neutral
    role = "uncertain_role"
    ws._manifold.set_manifold_vector(role, [0.5] * 16)

    # 3. Report success for this role
    sos.report_outcome("audit", success=True, details={"role": role})

    # 4. Verify role moved toward anchor (Reward)
    vec = ws._manifold.get_manifold_vector(role)
    assert vec[0] < 0.5


def test_policy_engine_restriction():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()

    # 1. High Pressure condition
    ws._energy.set_energy(10.0)
    # Fragment communities to increase pressure further
    ws._topology._communities = [{"a"}, {"b"}, {"c"}, {"d"}, {"e"}]
    pressure = ws.get_system_pressure()
    assert pressure > 1.5

    # 2. Register an action
    action_point = [1.0] * 16
    sos.register_action("urgent_verification", action_point, "plugin")

    # 3. Setup role at that point
    ws._manifold.set_manifold_vector("cost", action_point)
    ws._topology.add(["cost"], "500", instability=0.1)

    # 4. Trigger dispatch - should be blocked by policy
    triggered = sos.trigger_actions()
    assert triggered == 0
    assert len(ws._action.action_history) == 0
