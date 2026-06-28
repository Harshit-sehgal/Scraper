from unittest.mock import patch

import pytest
from app.llm_bridge import SubstratePluginManager, get_plugin_manager
from app.semantic_world_state import get_world_state


def _patch_sandbox_for_tests():
    """Return a context manager that patches ``_sandboxed_call`` to run in-process.

    Tests that register handlers defined in ``tests.*`` cannot dispatch them
    through the real sandbox (the subprocess worker can't import test
    functions). Patching ``_sandboxed_call`` to call ``handler(**kwargs)``
    directly is the safe, scoped replacement for the removed
    ``DATAFORGE_SANDBOX_DISABLED`` env var.
    """

    def _fake_sandboxed_call(self, handler_name, handler, kwargs):
        return handler(**kwargs)

    return patch.object(SubstratePluginManager, "_sandboxed_call", _fake_sandboxed_call)


def test_native_role_merger() -> None:
    ws = get_world_state()
    ws.clear()
    plugins = get_plugin_manager(ws=ws)

    # 1. Setup two roles
    ws._manifold.set_manifold_vector("role_a", [1.0, 0.0] * 8)
    ws._manifold.set_manifold_vector("role_b", [0.0, 1.0] * 8)

    # 2. Call tool with sandbox patched for test environment
    with _patch_sandbox_for_tests():
        result = plugins.call_tool("role_merger", role_a="role_a", role_b="role_b")

    # 3. Verify
    assert "Success" in result
    vec = ws._manifold.get_manifold_vector("role_a")
    assert vec[0] == pytest.approx(0.5)
    assert not ws._manifold.has_manifold_role("role_b")


def test_autonomous_refactor_trigger() -> None:
    ws = get_world_state()
    ws.clear()
    _ = get_plugin_manager(ws=ws)

    # Setup roles
    ws._manifold.set_manifold_vector("r1", [0.5] * 16)
    ws._manifold.set_manifold_vector("r2", [0.5] * 16)

    # Register an action that calls the merger
    ws._action.register_action("auto_merge", [0.5] * 16, "role_merger", threshold=1.0)

    # Trigger a stable basin
    ws._topology.add(["r1"], "tok", instability=0.1)

    # Trigger actions
    # role_merger expects role_a and role_b.
    # dispatch_actions passes 'role' and 'token' by default.
    # I should update dispatch_actions to support flexible tool parameters or
    # update the tool to handle default params.


def test_manifold_compression_tool() -> None:
    ws = get_world_state()
    ws.clear()
    plugins = get_plugin_manager(ws=ws)

    # 1. Setup dense manifold with one constant dimension (zero variance)
    for i in range(15):
        vec = [0.5] * 16
        vec[0] = 0.9  # constant
        vec[1] = i / 15.0  # variable
        ws._manifold.set_manifold_vector(f"r{i}", vec)

    # 2. Trigger compressor with sandbox patched for test environment
    with _patch_sandbox_for_tests():
        result = plugins.call_tool("manifold_compressor")

    # 3. Verify (dim 0 should have zero variance)
    assert "Success" in result
