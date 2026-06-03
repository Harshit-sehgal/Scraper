import pytest
from app.llm_bridge import get_plugin_manager
from app.semantic_os import get_semantic_os
from app.semantic_world_state import get_world_state


def test_plugin_registration_and_execution() -> None:
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()
    plugins = get_plugin_manager(ws=ws)

    # 1. Define and register a mock handler
    def mock_handler(role, token):
        return f"Processed {role} for {token}"

    plugins.register_handler("test_handler", mock_handler)

    # 2. Register an action tied to this handler
    action_point = [1.0, 0.0] * 8
    sos.register_action("trigger_test", action_point, "test_handler", threshold=0.5)

    # 3. Setup a stable basin to trigger the action
    ws._manifold.set_manifold_vector("target_role", action_point)
    ws._topology.add(["target_role"], "tok1", instability=0.1)

    # 4. Trigger dispatch
    triggered = sos.trigger_actions()

    # 5. Verify
    assert triggered == 1
    history = ws._action.action_history
    assert len(history) == 1
    assert "Processed target_role for tok1" in str(history[0]["details"]["tool_result"])


def test_plugin_policy_restriction() -> None:
    ws = get_world_state()
    ws.clear()
    plugins = get_plugin_manager(ws=ws)

    def mock_handler(role, token):
        return "ok"

    plugins.register_handler("p1", mock_handler)

    # Setup High Pressure
    ws._energy.set_energy(10.0)
    ws._topology._communities = [{"a"}, {"b"}, {"c"}, {"d"}, {"e"}]

    # Attempt tool call directly - should be blocked by policy (inherited from ws)
    with pytest.raises(PermissionError):
        plugins.call_tool("p1", role="r", token="t")
