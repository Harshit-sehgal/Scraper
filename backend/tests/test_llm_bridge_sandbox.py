"""Tests for LLM bridge sandbox — LAW 15 subprocess isolation enforcement.

Verifies that ``SubstratePluginManager.call_tool`` always dispatches
through ``_sandboxed_call`` and that ``_sandboxed_call`` rejects on
subprocess failures with ``SandboxError`` (fail-closed per LAW 15).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from app.llm_bridge import (
    ALLOWED_SANDBOX_MODULES,
    SubstratePluginManager,
    is_handler_module_allowed,
    reset_plugin_manager,
)


@pytest.fixture(autouse=True)
def _reset_pm():
    reset_plugin_manager()
    yield
    reset_plugin_manager()


def _register_allow_listed_handler(pm: SubstratePluginManager, name: str, handler):
    """Register a handler whose ``__module__`` is forced to be on the allow-list.

    The default ``__module__`` of a test fixture function (``tests.test_llm_bridge_sandbox``)
    is NOT in the allow-list (as expected — this is the security model). Tests
    that exercise the dispatch path therefore patch ``__module__`` to one of
    the allow-listed modules so the dispatch path actually runs.
    """
    handler.__module__ = "app.llm_bridge"  # always on the allow-list
    pm.register_handler(name, handler)


# ─── Allow-list allow-list / structural ─────────────────────────────────


def test_allow_list_immutable():
    """``ALLOWED_SANDBOX_MODULES`` should be a frozenset — accidentally
    mutating it would weaken the security model.
    """
    assert isinstance(ALLOWED_SANDBOX_MODULES, frozenset)
    with pytest.raises((AttributeError, TypeError)):
        ALLOWED_SANDBOX_MODULES.add("app.user")  # type: ignore[attr-defined]


def test_native_handlers_are_allow_listed():
    """The two built-in tools must be on the allow-list (otherwise
    SubstratePluginManager() would refuse to dispatch them).
    """
    pm = SubstratePluginManager()
    for handler_name in ("role_merger", "manifold_compressor"):
        handler = pm._handlers[handler_name]
        assert is_handler_module_allowed(handler), f"native handler {handler_name!r} should be on the allow-list"


def test_non_allow_listed_handler_is_refused():
    """A handler whose ``__module__`` is not in the allow-list must be rejected."""
    pm = SubstratePluginManager()
    handler = MagicMock(return_value="ok")
    handler.__module__ = "app.attacker"  # not allow-listed
    pm.register_handler("evil", handler)
    with pytest.raises(PermissionError, match="allow-list"):
        pm.call_tool("evil")


def test_builtin_modules_rejected():
    """``os``, ``subprocess``, ``builtins`` must all be rejected."""
    pm = SubstratePluginManager()
    for module_name in ("os", "subprocess", "builtins", "__main__", ""):
        handler = MagicMock(return_value="ok")
        handler.__module__ = module_name
        pm.register_handler(f"evil_{module_name or 'empty'}", handler)
        with pytest.raises(PermissionError):
            pm.call_tool(f"evil_{module_name or 'empty'}")


# ─── Existing sandbox-fail-closed contract ──────────────────────────────────


class TestSandboxCallInProcessPatch:
    """Tests that patch ``_sandboxed_call`` to run in-process for handlers
    whose subprocess is unavailable in test environments. This replaces the
    old ``DATAFORGE_SANDBOX_DISABLED`` env-var bypass with a targeted
    ``unittest.mock.patch.object`` on the instance method.
    """

    @pytest.fixture(autouse=True)
    def _enable_in_process_dispatch(self):
        """Patch _sandboxed_call to run handler(**kwargs) in-process.

        This fixture applies to every test in this class and is the
        canonical way to exercise the dispatch chain when subprocess
        isolation is unavailable (e.g., tests where qualname resolution
        fails across process boundaries).
        """

        def _fake_sandboxed_call(self, handler_name, handler, kwargs):
            return handler(**kwargs)

        with patch.object(SubstratePluginManager, "_sandboxed_call", _fake_sandboxed_call):
            yield

    def test_in_process_dispatch_on_patched_sandbox(self) -> None:
        """When _sandboxed_call is patched, the handler executes in-process."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="in-process-result")
        _register_allow_listed_handler(pm, "patched_tool", handler)

        result = pm.call_tool("patched_tool")

        assert result == "in-process-result"
        handler.assert_called_once()

    def test_in_process_dispatch_success_recorded(self) -> None:
        """call_tool records success in execution history with patched sandbox."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="ok")
        _register_allow_listed_handler(pm, "hist_tool", handler)

        pm.call_tool("hist_tool")

        assert len(pm._execution_history) == 1
        assert pm._execution_history[0]["handler"] == "hist_tool"
        assert pm._execution_history[0]["status"] == "success"

    def test_in_process_dispatch_error_recorded(self) -> None:
        """call_tool records errors in execution history with patched sandbox."""
        pm = SubstratePluginManager()

        def bad_handler():
            msg = "deliberate failure"
            raise RuntimeError(msg)

        _register_allow_listed_handler(pm, "bad_tool", bad_handler)

        with pytest.raises(RuntimeError, match="deliberate failure"):
            pm.call_tool("bad_tool")

        assert len(pm._execution_history) == 1
        assert pm._execution_history[0]["status"] == "error"

    def test_history_truncation_with_patched_sandbox(self) -> None:
        """History is truncated when it exceeds max size."""
        pm = SubstratePluginManager()
        pm._max_history = 4
        handler = MagicMock(return_value="ok")
        _register_allow_listed_handler(pm, "trunc_tool", handler)

        for _ in range(6):
            pm.call_tool("trunc_tool")

        assert len(pm._execution_history) <= 4

    def test_native_role_merger_with_patched_sandbox(self) -> None:
        """role_merger dispatches (and returns 'Fail: No WS') when sandbox is patched."""
        pm = SubstratePluginManager()
        result = pm.call_tool("role_merger")
        assert result == "Fail: No WS"


class TestSandboxRaisesOnFailure:
    """LAW 15 fail-closed: _sandboxed_call raises SandboxError on all
    subprocess failure modes — no in-process fallback is permitted.
    """

    def test_sandbox_error_on_os_error(self) -> None:
        from app.llm_bridge import SandboxError

        pm = SubstratePluginManager()
        handler = MagicMock()
        _register_allow_listed_handler(pm, "os_tool", handler)

        with patch("subprocess.run", side_effect=OSError("subprocess unavailable")):
            with pytest.raises(SandboxError, match="in-process fallback is disabled"):
                pm.call_tool("os_tool")

        # Handler must never execute in-process on sandbox failure
        handler.assert_not_called()

    def test_sandbox_error_on_timeout(self) -> None:
        import subprocess as sp

        from app.llm_bridge import SandboxError

        pm = SubstratePluginManager()
        handler = MagicMock()
        _register_allow_listed_handler(pm, "timeout_tool", handler)

        with patch(
            "subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="python", timeout=30),
        ):
            with pytest.raises(SandboxError, match="in-process fallback is disabled"):
                pm.call_tool("timeout_tool")

        handler.assert_not_called()

    def test_sandbox_error_on_nonzero_exit(self) -> None:
        from app.llm_bridge import SandboxError

        pm = SubstratePluginManager()
        handler = MagicMock()
        _register_allow_listed_handler(pm, "nonzero_tool", handler)

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "import error"
        mock_proc.stdout = ""

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(SandboxError, match="in-process fallback is disabled"):
                pm.call_tool("nonzero_tool")

        handler.assert_not_called()

    def test_sandbox_error_on_invalid_json(self) -> None:
        from app.llm_bridge import SandboxError

        pm = SubstratePluginManager()
        handler = MagicMock()
        _register_allow_listed_handler(pm, "json_tool", handler)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "not valid json"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(SandboxError, match="in-process fallback is disabled"):
                pm.call_tool("json_tool")

        handler.assert_not_called()

    def test_sandbox_error_on_ok_false(self) -> None:
        from app.llm_bridge import SandboxError

        pm = SubstratePluginManager()
        handler = MagicMock()
        _register_allow_listed_handler(pm, "bad_ok_tool", handler)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"ok": False, "result": "sandbox rejected"})
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(SandboxError, match="in-process fallback is disabled"):
                pm.call_tool("bad_ok_tool")

        handler.assert_not_called()


class TestGetPluginManager:
    """get_plugin_manager returns a singleton."""

    def test_singleton(self) -> None:
        from app.llm_bridge import get_plugin_manager

        pm1 = get_plugin_manager()
        pm2 = get_plugin_manager()
        assert pm1 is pm2

    def test_reset_clears_singleton(self) -> None:
        from app.llm_bridge import get_plugin_manager

        pm1 = get_plugin_manager()
        reset_plugin_manager()
        pm2 = get_plugin_manager()
        assert pm1 is not pm2
