"""Comprehensive Unit Tests for LLM Bridge.

Covers JSON extraction, HTTP retry logic, Groq/Pollinations/g4f fallback chains,
call counting, and the SubstratePluginManager.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

# ─── _extract_json_payload ─────────────────────────────────────────────
from app.llm_bridge import (
    SubstratePluginManager,
    _call_openai_compatible_json,
    _call_openai_compatible_text,
    _extract_json_payload,
    _groq_model_candidates,
    _record_llm_degradation,
    _should_retry_http_error,
    get_llm_call_count,
    get_plugin_manager,
    llm_json,
    llm_json_fast,
    llm_text,
    reset_llm_call_count,
    reset_plugin_manager,
)


class TestExtractJsonPayload:
    def test_none_or_empty(self) -> None:
        assert _extract_json_payload(None) is None
        assert _extract_json_payload("") is None
        assert _extract_json_payload("   ") is None

    def test_direct_json_object(self) -> None:
        result = _extract_json_payload('{"name": "Test", "price": 100}')
        assert result == {"name": "Test", "price": 100}

    def test_direct_json_array(self) -> None:
        result = _extract_json_payload('[{"a": 1}, {"b": 2}]')
        assert result == [{"a": 1}, {"b": 2}]

    def test_json_in_code_fence(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json_payload(text)
        assert result == {"key": "value"}

    def test_code_fence_without_json_tag(self) -> None:
        text = '```\n{"answer": 42}\n```'
        result = _extract_json_payload(text)
        assert result == {"answer": 42}

    def test_embedded_object_in_text(self) -> None:
        text = 'Here is the result: {"found": true, "count": 5}. End.'
        result = _extract_json_payload(text)
        assert result == {"found": True, "count": 5}

    def test_embedded_array_in_text(self) -> None:
        text = "Results: [1, 2, 3] are ready."
        result = _extract_json_payload(text)
        assert result == [1, 2, 3]

    def test_invalid_json_returns_none(self) -> None:
        result = _extract_json_payload("this is not json at all")
        assert result is None

    def test_nested_object(self) -> None:
        text = '{"level1": {"level2": [1, 2, 3]}}'
        result = _extract_json_payload(text)
        assert result == {"level1": {"level2": [1, 2, 3]}}


# ─── _should_retry_http_error ──────────────────────────────────────────


class TestShouldRetryHttpError:
    def test_retryable_http_status(self) -> None:
        for status in (429, 500, 502, 503, 504):
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = status
            err = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
            assert _should_retry_http_error(err), f"Status {status} should be retryable"

    def test_non_retryable_http_status(self) -> None:
        for status in (400, 401, 403, 404, 422, 501):
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = status
            err = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
            assert not _should_retry_http_error(err), f"Status {status} should NOT be retryable"

    def test_request_error_is_retryable(self) -> None:
        err = httpx.RequestError("Connection refused", request=MagicMock())
        assert _should_retry_http_error(err)

    def test_error_string_containing_retryable_token(self) -> None:
        for token in ("429", "timed out", "connection", "temporary"):
            err = RuntimeError(f"Something {token} happened")
            assert _should_retry_http_error(err), f"Error with '{token}' should be retryable"

    def test_error_without_retryable_token(self) -> None:
        err = RuntimeError("Invalid request")
        assert not _should_retry_http_error(err)

    def test_response_is_none(self) -> None:
        """HTTPStatusError with response=None should still check status code."""
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        err = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
        assert _should_retry_http_error(err)


# ─── _groq_model_candidates ────────────────────────────────────────────


class TestGroqModelCandidates:
    def test_defaults_when_no_env_vars(self) -> None:
        with (
            patch("app.llm_bridge.settings.GROQ_DEFAULT_MODEL", "llama-3.3-70b-versatile"),
            patch("app.llm_bridge.settings.GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant"),
        ):
            models = _groq_model_candidates()
            assert models == ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    def test_uses_settings(self) -> None:
        with (
            patch("app.llm_bridge.settings.GROQ_DEFAULT_MODEL", "mixtral-8x7b-32768"),
            patch("app.llm_bridge.settings.GROQ_FALLBACK_MODEL", "llama2-70b-4096"),
        ):
            models = _groq_model_candidates()
            assert models == ["mixtral-8x7b-32768", "llama2-70b-4096"]

    def test_deduplicates_identical_models(self) -> None:
        with (
            patch("app.llm_bridge.settings.GROQ_DEFAULT_MODEL", "llama-3.3-70b-versatile"),
            patch("app.llm_bridge.settings.GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile"),
        ):
            models = _groq_model_candidates()
            assert models == ["llama-3.3-70b-versatile"]  # Deduplicated

    def test_uses_defaults_on_none(self) -> None:
        with patch("app.llm_bridge.settings.GROQ_DEFAULT_MODEL", ""), patch("app.llm_bridge.settings.GROQ_FALLBACK_MODEL", ""):
            models = _groq_model_candidates()
            # Empty strings resolve to defaults due to `or` operator
            assert models == ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


# ─── _record_llm_degradation ───────────────────────────────────────────


class TestRecordLlmDegradation:
    def test_records_degradation(self) -> None:
        ws_mock = MagicMock()
        with patch("app.semantic_world_state.get_world_state", return_value=ws_mock):
            _record_llm_degradation("groq", "API timeout", severity="critical")
            ws_mock.record_degradation.assert_called_once_with(subsystem="groq", severity="critical", cause="API timeout")

    def test_handles_world_state_unavailable(self) -> None:
        with patch("app.semantic_world_state.get_world_state", side_effect=Exception("No WS")):
            _record_llm_degradation("test", "failure")  # Should not raise


# ─── Call Counting ─────────────────────────────────────────────────────


class TestCallCounting:
    def setup_method(self):
        reset_llm_call_count()

    def test_initial_count_is_zero(self) -> None:
        assert get_llm_call_count() == 0

    def test_reset_works(self) -> None:
        from app.llm_bridge import _record_call

        _record_call()
        _record_call()
        assert get_llm_call_count() == 2
        reset_llm_call_count()
        assert get_llm_call_count() == 0


# ─── HTTP-level helpers (_call_openai_compatible_json/_text) ───────────


class _MockAsyncClient:
    """Helper: creates an async client mock whose post() returns awaitable responses."""

    def __init__(self, response_sequence=None):
        # response_sequence: list of response objects or callables that return responses
        self.response_sequence = response_sequence or []
        self.call_count = 0
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, endpoint, json=None, headers=None):
        self.call_count += 1
        self.posts.append((endpoint, json, headers))
        if self.response_sequence:
            idx = min(self.call_count - 1, len(self.response_sequence) - 1)
            item = self.response_sequence[idx]
            if isinstance(item, MagicMock):
                return item
            if callable(item):
                return item()
            return item
        # Default: return a response with empty data
        resp = MagicMock()
        resp.json.return_value = {"choices": [{"message": {"content": ""}}]}
        return resp


class TestCallOpenaiCompatibleJson:
    @pytest.mark.asyncio
    async def test_successful_call(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"key": "value"}'}}]}

        with patch("app.llm_bridge.httpx.AsyncClient", return_value=_MockAsyncClient([mock_response])):
            result = await _call_openai_compatible_json("http://endpoint", {"model": "test"}, timeout=10)
            assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_retry_on_500(self) -> None:
        mock_client = _MockAsyncClient()

        mock_fail = MagicMock(spec=httpx.Response)
        mock_fail.status_code = 500
        mock_fail.raise_for_status.side_effect = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_fail)

        mock_success = MagicMock()
        mock_success.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}

        mock_client.response_sequence = [mock_fail, mock_success]

        with patch("app.llm_bridge.httpx.AsyncClient", return_value=mock_client):
            result = await _call_openai_compatible_json(
                "http://endpoint", {"model": "test"}, timeout=10, max_attempts=2, backoff_seconds=0.01
            )
            assert result == {"ok": True}
            assert mock_client.call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises(self) -> None:
        mock_client = _MockAsyncClient()

        mock_bad = MagicMock(spec=httpx.Response)
        mock_bad.status_code = 400
        mock_bad.raise_for_status.side_effect = httpx.HTTPStatusError("Bad request", request=MagicMock(), response=mock_bad)

        mock_client.response_sequence = [mock_bad]

        with patch("app.llm_bridge.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await _call_openai_compatible_json("http://endpoint", {"model": "test"}, timeout=10, max_attempts=2)
            assert mock_client.call_count == 1  # No retry on 400


class TestCallOpenaiCompatibleText:
    @pytest.mark.asyncio
    async def test_successful_call(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "  Hello World  "}}]}

        with patch("app.llm_bridge.httpx.AsyncClient", return_value=_MockAsyncClient([mock_response])):
            result = await _call_openai_compatible_text("http://endpoint", {"model": "test"}, timeout=10)
            assert result == "Hello World"  # Stripped

    @pytest.mark.asyncio
    async def test_empty_content_returns_empty_string(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": ""}}]}

        with patch("app.llm_bridge.httpx.AsyncClient", return_value=_MockAsyncClient([mock_response])):
            result = await _call_openai_compatible_text("http://endpoint", {"model": "test"}, timeout=10)
            assert result == ""


# ─── llm_json / llm_json_fast / llm_text ───────────────────────────────


class TestLlmJson:
    @pytest.mark.asyncio
    async def test_groq_success(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with (
                patch("app.llm_bridge._groq_model_candidates", return_value=["llama-3.3-70b-versatile"]),
                patch("app.llm_bridge._call_openai_compatible_json", return_value={"result": "groq_ok"}) as mock_call,
            ):
                result = await llm_json([{"role": "user", "content": "hi"}])
                assert result == {"result": "groq_ok"}
                mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_groq_fails_then_pollinations(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with (
                patch("app.llm_bridge._groq_model_candidates", return_value=["llama-3.3-70b-versatile"]),
                patch("app.llm_bridge._call_openai_compatible_json") as mock_call,
                patch("app.llm_bridge.settings.GROQ_API_ENDPOINT", "http://groq"),
                patch("app.llm_bridge.settings.POLLINATIONS_API_ENDPOINT", "http://polli"),
                patch("app.llm_bridge.settings.LLM_ENABLE_PUBLIC_FALLBACKS", True),
            ):
                # Groq fails, Pollinations succeeds
                mock_call.side_effect = [
                    None,  # Groq returns None -> fails
                    {"result": "polli_ok"},  # Pollinations succeeds
                ]

                result = await llm_json([{"role": "user", "content": "hi"}])
                assert result == {"result": "polli_ok"}
                assert mock_call.call_count == 2

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_empty_dict(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),  # No GROQ key
            patch("app.llm_bridge._call_openai_compatible_json", side_effect=Exception("API error")),
            patch("app.llm_bridge.settings.POLLINATIONS_API_ENDPOINT", "http://polli"),
            patch("app.llm_bridge.asyncio.to_thread", side_effect=Exception("g4f error")),
            patch("app.llm_bridge._record_llm_degradation"),
        ):
            result = await llm_json([{"role": "user", "content": "hi"}])
            assert result == {}  # Empty dict fallback

    @pytest.mark.asyncio
    async def test_public_fallbacks_disabled_skips_unauthenticated_http(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.llm_bridge._call_openai_compatible_json") as mock_json,
            patch("app.llm_bridge.asyncio.to_thread") as mock_thread,
            patch("app.llm_bridge.settings.LLM_ENABLE_PUBLIC_FALLBACKS", False),
        ):
            result = await llm_json([{"role": "user", "content": "hi"}])
            assert result == {}
            mock_json.assert_not_called()
            mock_thread.assert_not_called()


class TestLlmJsonFast:
    @pytest.mark.asyncio
    async def test_groq_success(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with (
                patch("app.llm_bridge._groq_model_candidates", return_value=["llama-3.3-70b-versatile"]),
                patch("app.llm_bridge._call_openai_compatible_json", return_value={"ok": True}) as mock_call,
            ):
                result = await llm_json_fast([{"role": "user", "content": "hi"}])
                assert result == {"ok": True}
                mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_fail_returns_empty_dict(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.llm_bridge._call_openai_compatible_json", side_effect=Exception("fail")),
            patch("app.llm_bridge.settings.POLLINATIONS_API_ENDPOINT", "http://polli"),
            patch("app.llm_bridge._record_llm_degradation"),
            patch("app.llm_bridge.settings.LLM_ENABLE_PUBLIC_FALLBACKS", True),
        ):
            result = await llm_json_fast([{"role": "user", "content": "hi"}])
            assert result == {}


class TestLlmText:
    @pytest.mark.asyncio
    async def test_groq_success(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with (
                patch("app.llm_bridge._groq_model_candidates", return_value=["llama-3.3-70b-versatile"]),
                patch("app.llm_bridge._call_openai_compatible_text", return_value="Hello from Groq") as mock_call,
            ):
                result = await llm_text([{"role": "user", "content": "hi"}])
                assert result == "Hello from Groq"
                mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_response_when_all_fail(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.llm_bridge._call_openai_compatible_text", side_effect=Exception("fail")),
            patch("app.llm_bridge.settings.POLLINATIONS_API_ENDPOINT", "http://polli"),
            patch("app.llm_bridge.asyncio.to_thread", side_effect=Exception("g4f fail")),
            patch("app.llm_bridge._record_llm_degradation"),
            patch("app.llm_bridge.settings.LLM_ENABLE_PUBLIC_FALLBACKS", True),
        ):
            result = await llm_text([{"role": "user", "content": "hi"}])
            assert result == ""


# ─── SubstratePluginManager ────────────────────────────────────────────


class TestSubstratePluginManager:
    def setup_method(self):
        reset_plugin_manager()

    def test_register_handler(self) -> None:
        mgr = SubstratePluginManager()

        def handler(**kwargs):
            return "ok"

        mgr.register_handler("test_handler", handler)
        assert "test_handler" in mgr.get_available_tools()

    def test_call_tool_executes_handler(self) -> None:
        mgr = SubstratePluginManager()

        def handler(**kwargs):
            return f"processed {kwargs.get('x')}"

        mgr.register_handler("echo", handler)
        result = mgr.call_tool("echo", x=42)
        assert result == "processed 42"

    def test_call_tool_unknown_handler(self) -> None:
        mgr = SubstratePluginManager()
        with pytest.raises(ValueError, match="Unknown handler"):
            mgr.call_tool("nonexistent")

    def test_call_tool_records_execution_history(self) -> None:
        mgr = SubstratePluginManager()

        def handler(**kwargs):
            return "done"

        mgr.register_handler("h1", handler)
        mgr.call_tool("h1", foo="bar")
        assert len(mgr._execution_history) == 1
        assert mgr._execution_history[0]["handler"] == "h1"
        assert mgr._execution_history[0]["status"] == "success"

    def test_call_tool_records_failure_in_history(self) -> None:
        mgr = SubstratePluginManager()

        def handler(**kwargs):
            raise ValueError("oops")

        mgr.register_handler("failing", handler)
        with pytest.raises(ValueError):
            mgr.call_tool("failing")
        assert mgr._execution_history[0]["status"] == "error"

    def test_call_tool_respects_policy_block(self) -> None:
        ws_mock = MagicMock()
        ws_mock.get_system_pressure.return_value = 0.9

        mgr = SubstratePluginManager(ws=ws_mock)

        def handler(**kwargs):
            return "should not reach"

        mgr.register_handler("blocked", handler)

        with patch("app.policy_engine.get_policy_engine") as mock_policy:
            policy_instance = MagicMock()
            policy_instance.can_dispatch_action.return_value = False
            mock_policy.return_value = policy_instance

            with pytest.raises(PermissionError, match="blocked by substrate policy"):
                mgr.call_tool("blocked")

            policy_instance.can_dispatch_action.assert_called_once()

    def test_native_role_merger_no_ws(self) -> None:
        mgr = SubstratePluginManager(ws=None)
        result = mgr._native_role_merger(role_a="a", role_b="b")
        assert "Fail" in result

    def test_native_role_merger_missing_roles(self) -> None:
        ws_mock = MagicMock()
        mgr = SubstratePluginManager(ws=ws_mock)
        result = mgr._native_role_merger(role_a=None, role_b="b")
        assert "Fail" in result

    def test_native_role_merger_success(self) -> None:
        ws_mock = MagicMock()
        ws_mock.role_manifold = {
            "role_a": [1.0, 0.0] * 8,
            "role_b": [0.0, 1.0] * 8,
        }
        ws_mock.manifold_dimension = 16

        mgr = SubstratePluginManager(ws=ws_mock)
        with ws_mock.transaction:
            result = mgr._native_role_merger(role_a="role_a", role_b="role_b")
            assert "Success" in result
            ws_mock.set_manifold_vector.assert_called_once()
            ws_mock.remove_manifold_role.assert_called_once_with("role_b")

    def test_native_manifold_compressor_sparse(self) -> None:
        ws_mock = MagicMock()
        ws_mock.role_manifold = {"r1": [0.5] * 16}
        ws_mock.manifold_dimension = 16

        # len(manifold) < 10 -> skip
        mgr = SubstratePluginManager(ws=ws_mock)
        result = mgr._native_manifold_compressor()
        assert "Skip" in result

    def test_native_manifold_compressor_dense(self) -> None:
        ws_mock = MagicMock()
        ws_mock.role_manifold = {f"r{i}": [0.5] * 16 for i in range(15)}
        # Make dimension 0 constant (zero variance)
        for i in range(15):
            ws_mock.role_manifold[f"r{i}"][0] = 0.9
        ws_mock.manifold_dimension = 16

        mgr = SubstratePluginManager(ws=ws_mock)
        result = mgr._native_manifold_compressor()
        assert "Success" in result

    def test_get_available_tools_includes_native(self) -> None:
        mgr = SubstratePluginManager()
        tools = mgr.get_available_tools()
        assert "role_merger" in tools
        assert "manifold_compressor" in tools


class TestGetPluginManager:
    def setup_method(self):
        reset_plugin_manager()

    def test_singleton_behavior(self) -> None:
        first = get_plugin_manager()
        second = get_plugin_manager()
        assert first is second

    def test_reset_works(self) -> None:
        first = get_plugin_manager()
        reset_plugin_manager()
        second = get_plugin_manager()
        assert first is not second
