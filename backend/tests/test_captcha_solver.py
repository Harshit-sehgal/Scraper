"""Tests for the CAPTCHA solver adapter system.

Validates:
1. _NoOpSolver returns None / False
2. Factory returns _NoOpSolver when disabled
3. Factory returns appropriate solver when enabled with a key
4. _TwoCaptchaSolver constructs and maps methods
5. _AntiCaptchaSolver constructs and maps task types
6. reset_captcha_solver clears the singleton
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.captcha_solver import (
    _AntiCaptchaSolver,
    _NoOpSolver,
    _TwoCaptchaSolver,
    get_captcha_solver,
    reset_captcha_solver,
)


def _mock_resp(status: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    resp.aclose = AsyncMock()
    return resp


@pytest.fixture(autouse=True)
def _reset_solver():
    """Reset the module-level solver singleton before each test."""
    reset_captcha_solver()
    yield
    reset_captcha_solver()


# ---------------------------------------------------------------------------
# _NoOpSolver
# ---------------------------------------------------------------------------


class TestNoOpSolver:
    @pytest.mark.asyncio
    async def test_solve_returns_none(self) -> None:
        solver = _NoOpSolver()
        result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_healthcheck_returns_false(self) -> None:
        solver = _NoOpSolver()
        assert await solver.healthcheck() is False


# ---------------------------------------------------------------------------
# _TwoCaptchaSolver
# ---------------------------------------------------------------------------


class TestTwoCaptchaSolver:
    def test_constructs_with_key(self) -> None:
        solver = _TwoCaptchaSolver("my-api-key", timeout_s=60)
        assert solver._api_key == "my-api-key"
        assert solver._timeout_s == 60

    def test_method_mapping(self) -> None:
        assert _TwoCaptchaSolver._map_method("recaptcha") == "userrecaptcha"
        assert _TwoCaptchaSolver._map_method("hcaptcha") == "hcaptcha"
        assert _TwoCaptchaSolver._map_method("turnstile") == "turnstile"
        assert _TwoCaptchaSolver._map_method("unknown") == "userrecaptcha"

    @pytest.mark.asyncio
    async def test_solve_returns_none_on_timeout(self) -> None:
        """Timeout should return None gracefully."""
        from unittest.mock import AsyncMock, MagicMock, patch

        def _mock_resp(status: int, json_data: dict) -> MagicMock:
            resp = MagicMock()
            resp.status_code = status
            resp.json.return_value = json_data
            resp.raise_for_status.return_value = None
            resp.aclose = AsyncMock()
            return resp

        solver = _TwoCaptchaSolver("fake-key", timeout_s=1)
        mock_client = MagicMock(spec=["post", "get"])
        mock_client.post.return_value = _mock_resp(200, {"status": 1, "request": "12345"})
        mock_client.get.return_value = _mock_resp(200, {"status": 0, "request": "CAPCHA_NOT_READY"})
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_solve_returns_none_on_http_error(self) -> None:
        """Service-unavailable (HTTP error) should return None gracefully."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        solver = _TwoCaptchaSolver("fake-key", timeout_s=30)
        mock_client = MagicMock(spec=["post", "get"])
        mock_client.post.side_effect = httpx.HTTPError("Service unavailable")
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None


# ---------------------------------------------------------------------------
# _AntiCaptchaSolver
# ---------------------------------------------------------------------------


class TestAntiCaptchaSolver:
    def test_constructs_with_key(self) -> None:
        solver = _AntiCaptchaSolver("my-anti-key", timeout_s=90)
        assert solver._api_key == "my-anti-key"
        assert solver._timeout_s == 90

    def test_task_type_mapping(self) -> None:
        assert _AntiCaptchaSolver._map_task_type("recaptcha") == "NoCaptchaTaskProxyless"
        assert _AntiCaptchaSolver._map_task_type("hcaptcha") == "HCaptchaTaskProxyless"
        assert _AntiCaptchaSolver._map_task_type("turnstile") == "TurnstileTaskProxyless"
        assert _AntiCaptchaSolver._map_task_type("unknown") == "NoCaptchaTaskProxyless"

    @pytest.mark.asyncio
    async def test_solve_returns_none_on_timeout(self) -> None:
        """Anti-Captcha poll loop timeout should return None gracefully."""
        from unittest.mock import AsyncMock, MagicMock, patch

        def _mock_resp(status: int, json_data: dict) -> MagicMock:
            resp = MagicMock()
            resp.status_code = status
            resp.json.return_value = json_data
            resp.raise_for_status.return_value = None
            resp.aclose = AsyncMock()
            return resp

        solver = _AntiCaptchaSolver("fake-key", timeout_s=1)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.side_effect = [
            _mock_resp(200, {"errorId": 0, "taskId": 999}),
            _mock_resp(200, {"errorId": 0, "status": "processing"}),
        ]
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_solve_returns_none_on_http_error(self) -> None:
        """Anti-Captcha service unavailable (HTTP error) should return None."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        solver = _AntiCaptchaSolver("fake-key", timeout_s=30)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.side_effect = httpx.HTTPError("Service unavailable")
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_returns_noop_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", False)
        solver = get_captcha_solver()
        assert isinstance(solver, _NoOpSolver)

    def test_returns_noop_when_enabled_but_empty_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_API_KEY", "")
        monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "2captcha")
        solver = get_captcha_solver()
        assert isinstance(solver, _NoOpSolver)

    def test_returns_two_captcha_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_API_KEY", "fake-key-123")
        monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "2captcha")
        solver = get_captcha_solver()
        assert isinstance(solver, _TwoCaptchaSolver)

    def test_returns_anticaptcha_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_API_KEY", "fake-key-456")
        monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "anticaptcha")
        solver = get_captcha_solver()
        assert isinstance(solver, _AntiCaptchaSolver)

    def test_unknown_provider_falls_back_to_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", True)
        monkeypatch.setattr(settings, "CAPTCHA_API_KEY", "fake-key-789")
        monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "unknown_provider")
        solver = get_captcha_solver()
        assert isinstance(solver, _NoOpSolver)

    def test_singleton_is_reused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CAPTCHA_SOLVER_ENABLED", False)
        solver1 = get_captcha_solver()
        solver2 = get_captcha_solver()
        assert solver1 is solver2


# ═══════════════════════════════════════════════════════════════════════
# Additional Coverage — Timeout, service unavailable, concurrent, no solution, fallback
# ═══════════════════════════════════════════════════════════════════════


class TestTwoCaptchaExtended:
    @pytest.mark.asyncio
    async def test_solve_returns_none_without_httpx(self) -> None:
        with pytest.MonkeyPatch.context() as mp:
            import builtins

            original_import = builtins.__import__

            def _no_httpx(name, *args, **kwargs):
                if name == "httpx":
                    _err_msg = "no httpx"
                    raise ImportError(_err_msg)
                return original_import(name, *args, **kwargs)

            mp.setattr(builtins, "__import__", _no_httpx)
            solver = _TwoCaptchaSolver("key", timeout_s=10)
            result = await solver.solve(site_key="abc", page_url="https://x.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_healthcheck_returns_false_without_httpx(self) -> None:
        with pytest.MonkeyPatch.context() as mp:
            import builtins

            original_import = builtins.__import__

            def _no_httpx(name, *args, **kwargs):
                if name == "httpx":
                    _err_msg = "no httpx"
                    raise ImportError(_err_msg)
                return original_import(name, *args, **kwargs)

            mp.setattr(builtins, "__import__", _no_httpx)
            solver = _TwoCaptchaSolver("key", timeout_s=10)
            assert await solver.healthcheck() is False

    @pytest.mark.asyncio
    async def test_solve_submit_error_returns_none(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _TwoCaptchaSolver("key", timeout_s=10)
        mock_client = MagicMock(spec=["post", "get"])
        mock_client.post.return_value = _mock_resp(200, {"status": 0, "request": "ERROR_BAD_KEY"})
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_solve_poll_error_returns_none(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _TwoCaptchaSolver("key", timeout_s=10)
        mock_client = MagicMock(spec=["post", "get"])
        mock_client.post.return_value = _mock_resp(200, {"status": 1, "request": "12345"})
        mock_client.get.return_value = _mock_resp(200, {"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_solve_success_path(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _TwoCaptchaSolver("key", timeout_s=30)
        mock_client = MagicMock(spec=["post", "get"])
        mock_client.post.return_value = _mock_resp(200, {"status": 1, "request": "task_42"})
        mock_client.get.return_value = _mock_resp(200, {"status": 1, "request": "SOLVED_TOKEN_XYZ"})
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result == "SOLVED_TOKEN_XYZ"


class TestAntiCaptchaExtended:
    @pytest.mark.asyncio
    async def test_solve_returns_none_without_httpx(self) -> None:
        with pytest.MonkeyPatch.context() as mp:
            import builtins

            original_import = builtins.__import__

            def _no_httpx(name, *args, **kwargs):
                if name == "httpx":
                    _err_msg = "no httpx"
                    raise ImportError(_err_msg)
                return original_import(name, *args, **kwargs)

            mp.setattr(builtins, "__import__", _no_httpx)
            solver = _AntiCaptchaSolver("key", timeout_s=10)
            result = await solver.solve(site_key="abc", page_url="https://x.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_healthcheck_returns_false_without_httpx(self) -> None:
        with pytest.MonkeyPatch.context() as mp:
            import builtins

            original_import = builtins.__import__

            def _no_httpx(name, *args, **kwargs):
                if name == "httpx":
                    _err_msg = "no httpx"
                    raise ImportError(_err_msg)
                return original_import(name, *args, **kwargs)

            mp.setattr(builtins, "__import__", _no_httpx)
            solver = _AntiCaptchaSolver("key", timeout_s=10)
            assert await solver.healthcheck() is False

    @pytest.mark.asyncio
    async def test_solve_create_task_error_returns_none(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _AntiCaptchaSolver("key", timeout_s=10)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.return_value = _mock_resp(200, {"errorId": 1, "errorDescription": "KEY_DOES_NOT_EXIST"})
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_solve_poll_error_returns_none(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _AntiCaptchaSolver("key", timeout_s=10)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.side_effect = [
            _mock_resp(200, {"errorId": 0, "taskId": 999}),
            _mock_resp(200, {"errorId": 1, "errorDescription": "ERROR_TASK_NOT_FOUND"}),
        ]
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_solve_success_path(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _AntiCaptchaSolver("key", timeout_s=30)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.side_effect = [
            _mock_resp(200, {"errorId": 0, "taskId": 1001}),
            _mock_resp(200, {"errorId": 0, "status": "ready", "solution": {"gRecaptchaResponse": "ANTI_TOKEN_ABC"}}),
        ]
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result == "ANTI_TOKEN_ABC"

    @pytest.mark.asyncio
    async def test_solve_success_with_token_field(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _AntiCaptchaSolver("key", timeout_s=30)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.side_effect = [
            _mock_resp(200, {"errorId": 0, "taskId": 1002}),
            _mock_resp(200, {"errorId": 0, "status": "ready", "solution": {"token": "TURNSTILE_TOKEN"}}),
        ]
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com", captcha_type="turnstile")
        assert result == "TURNSTILE_TOKEN"

    @pytest.mark.asyncio
    async def test_solve_returns_none_on_http_error(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        import httpx

        solver = _AntiCaptchaSolver("key", timeout_s=30)
        mock_client = MagicMock(spec=["post"])
        mock_client.post.side_effect = httpx.HTTPError("Service down")
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None


class TestConcurrentCaptchaRequests:
    @pytest.mark.asyncio
    async def test_concurrent_noop_solve(self) -> None:
        import asyncio

        solver = _NoOpSolver()
        results = await asyncio.gather(
            solver.solve(site_key="a", page_url="https://x.com"),
            solver.solve(site_key="b", page_url="https://y.com"),
            solver.solve(site_key="c", page_url="https://z.com"),
        )
        assert results == [None, None, None]

    @pytest.mark.asyncio
    async def test_concurrent_healthcheck(self) -> None:
        import asyncio

        solver = _NoOpSolver()
        results = await asyncio.gather(
            solver.healthcheck(),
            solver.healthcheck(),
            solver.healthcheck(),
        )
        assert results == [False, False, False]


class TestCaptchaSolverNoSolution:
    @pytest.mark.asyncio
    async def test_two_captcha_no_solution_on_poll_error(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        solver = _TwoCaptchaSolver("key", timeout_s=5)
        mock_client = MagicMock(spec=["post", "get"])
        mock_client.post.return_value = _mock_resp(200, {"status": 1, "request": "555"})
        mock_client.get.return_value = _mock_resp(200, {"status": 0, "request": "CAPCHA_NOT_READY"})
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_client

        with patch("app.url_safety.get_safe_async_client", return_value=mock_context):
            result = await solver.solve(site_key="abc", page_url="https://x.com")
        assert result is None


class TestFactoryExtended:
    def test_reset_then_get_creates_fresh_singleton(self) -> None:
        from app.config import settings

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, "CAPTCHA_SOLVER_ENABLED", False)
            s1 = get_captcha_solver()
            reset_captcha_solver()
            s2 = get_captcha_solver()
            assert s1 is not s2
            assert isinstance(s2, _NoOpSolver)
