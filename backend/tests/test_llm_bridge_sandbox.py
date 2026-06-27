"""Tests for LLM bridge sandbox — LAW 15 subprocess isolation enforcement.

Verifies that ``SubstratePluginManager.call_tool`` attempts subprocess
sandboxing through the allow-list handler modules, refuses non-allow-listed
handlers, and falls back gracefully on subprocess errors for allow-listed handlers.
"""

from __future__ import annotations

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
        assert is_handler_module_allowed(handler), (
            f"native handler {handler_name!r} should be on the allow-list"
        )


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


# ─── Existing sandbox-fallback contract ──────────────────────────────────


class TestSandboxCall:
    """_sandboxed_call attempts subprocess then falls back."""

    def test_fallback_to_in_process_on_subprocess_error(self) -> None:
        """When subprocess.run raises OSError, the allow-listed handler runs in-process."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="in-process-result")
        _register_allow_listed_handler(pm, "fallback_tool", handler)

        with patch("subprocess.run", side_effect=OSError("subprocess unavailable")):
            result = pm.call_tool("fallback_tool")

        assert result == "in-process-result"
        handler.assert_called_once()

    def test_fallback_on_subprocess_timeout(self) -> None:
        """When subprocess times out, an allow-listed handler runs in-process."""
        import subprocess

        pm = SubstratePluginManager()
        handler = MagicMock(return_value="timeout-fallback")
        _register_allow_listed_handler(pm, "timeout_tool", handler)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="python", timeout=30)):
            result = pm.call_tool("timeout_tool")

        assert result == "timeout-fallback"
        handler.assert_called_once()

    def test_fallback_on_nonzero_exit(self) -> None:
        """When subprocess exits non-zero (but worker did NOT refuse), allow-listed handler runs in-process."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="nonzero-fallback")
        _register_allow_listed_handler(pm, "nonzero_tool", handler)

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "import error"
        mock_proc.stdout = ""

        # Non-allow-listed handlers now raise PermissionError on the
        # top-level guard before reaching the subprocess.  Allow-listed
        # handlers still get the fallback path.
        with patch("subprocess.run", return_value=mock_proc):
            result = pm.call_tool("nonzero_tool")

        assert result == "nonzero-fallback"

    def test_fallback_on_invalid_json_output(self) -> None:
        """Allow-listed handler runs in-process when subprocess returns non-JSON."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="bad-json-fallback")
        _register_allow_listed_handler(pm, "bad_json_tool", handler)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "not valid json"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = pm.call_tool("bad_json_tool")

        assert result == "bad-json-fallback"


class TestExecutionHistory:
    """call_tool records result in execution history."""

    def test_success_recorded_in_history(self) -> None:
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="ok")
        _register_allow_listed_handler(pm, "hist_tool", handler)

        with patch("subprocess.run", side_effect=OSError("sandbox unavailable")):
            pm.call_tool("hist_tool")

        assert len(pm._execution_history) == 1
        assert pm._execution_history[0]["handler"] == "hist_tool"
        assert pm._execution_history[0]["status"] == "success"

    def test_error_recorded_in_history(self) -> None:
        pm = SubstratePluginManager()

        def bad_handler():
            msg = "deliberate failure"
            raise RuntimeError(msg)

        _register_allow_listed_handler(pm, "bad_tool", bad_handler)

        with patch("subprocess.run", side_effect=OSError("sandbox unavailable")):
            with pytest.raises(RuntimeError, match="deliberate failure"):
                pm.call_tool("bad_tool")

        assert len(pm._execution_history) == 1
        assert pm._execution_history[0]["status"] == "error"

    def test_history_truncation(self) -> None:
        """History is truncated when it exceeds max size."""
        pm = SubstratePluginManager()
        pm._max_history = 4
        handler = MagicMock(return_value="ok")
        _register_allow_listed_handler(pm, "trunc_tool", handler)

        with patch("subprocess.run", side_effect=OSError("sandbox unavailable")):
            for _ in range(6):
                pm.call_tool("trunc_tool")

        assert len(pm._execution_history) <= 4


class TestNativeTools:
    """Built-in native tools register and execute successfully."""

    def test_role_merger_registered(self) -> None:
        pm = SubstratePluginManager()
        assert "role_merger" in pm.get_available_tools()

    def test_manifold_compressor_registered(self) -> None:
        pm = SubstratePluginManager()
        assert "manifold_compressor" in pm.get_available_tools()

    def test_role_merger_no_ws(self) -> None:
        pm = SubstratePluginManager()
        with patch("subprocess.run", side_effect=OSError("sandbox unavailable")):
            result = pm.call_tool("role_merger")
        assert result == "Fail: No WS"


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
