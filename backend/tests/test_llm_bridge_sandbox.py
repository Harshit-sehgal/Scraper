"""Tests for LLM bridge sandbox — LAW 15 subprocess isolation enforcement.

Verifies that ``SubstratePluginManager.call_tool`` attempts subprocess
sandboxing before falling back to in-process execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.llm_bridge import SubstratePluginManager, reset_plugin_manager


@pytest.fixture(autouse=True)
def _reset_pm():
    reset_plugin_manager()
    yield
    reset_plugin_manager()


class TestSubstratePluginManagerRegistration:
    """Plugin registration and tool listing."""

    def test_register_handler(self) -> None:
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="ok")
        pm.register_handler("test_tool", handler)
        assert "test_tool" in pm.get_available_tools()

    def test_call_unknown_handler_raises(self) -> None:
        pm = SubstratePluginManager()
        with pytest.raises(ValueError, match="Unknown handler"):
            pm.call_tool("nonexistent")


class TestSandboxCall:
    """_sandboxed_call attempts subprocess then falls back."""

    def test_fallback_to_in_process_on_subprocess_error(self) -> None:
        """When subprocess.run raises OSError, handler runs in-process."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="in-process-result")
        pm.register_handler("fallback_tool", handler)

        with patch("subprocess.run", side_effect=OSError("subprocess unavailable")):
            result = pm.call_tool("fallback_tool")

        assert result == "in-process-result"
        handler.assert_called_once()

    def test_fallback_on_subprocess_timeout(self) -> None:
        """When subprocess times out, handler runs in-process."""
        import subprocess

        pm = SubstratePluginManager()
        handler = MagicMock(return_value="timeout-fallback")
        pm.register_handler("timeout_tool", handler)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="python", timeout=30)):
            result = pm.call_tool("timeout_tool")

        assert result == "timeout-fallback"
        handler.assert_called_once()

    def test_fallback_on_nonzero_exit(self) -> None:
        """When subprocess exits non-zero, handler runs in-process."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="nonzero-fallback")
        pm.register_handler("nonzero_tool", handler)

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "import error"
        mock_proc.stdout = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = pm.call_tool("nonzero_tool")

        assert result == "nonzero-fallback"

    def test_fallback_on_invalid_json_output(self) -> None:
        """When subprocess returns non-JSON, handler runs in-process."""
        pm = SubstratePluginManager()
        handler = MagicMock(return_value="bad-json-fallback")
        pm.register_handler("bad_json_tool", handler)

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
        pm.register_handler("hist_tool", lambda: "ok")

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

        pm.register_handler("bad_tool", bad_handler)

        with patch("subprocess.run", side_effect=OSError("sandbox unavailable")):
            with pytest.raises(RuntimeError, match="deliberate failure"):
                pm.call_tool("bad_tool")

        assert len(pm._execution_history) == 1
        assert pm._execution_history[0]["status"] == "error"

    def test_history_truncation(self) -> None:
        """History is truncated when it exceeds max size."""
        pm = SubstratePluginManager()
        pm._max_history = 4
        pm.register_handler("trunc_tool", lambda: "ok")

        with patch("subprocess.run", side_effect=OSError("sandbox unavailable")):
            for _ in range(6):
                pm.call_tool("trunc_tool")

        assert len(pm._execution_history) <= 4


class TestNativeTools:
    """Built-in native tools register successfully."""

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
