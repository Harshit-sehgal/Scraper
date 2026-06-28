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

import pytest
from app.captcha_solver import (
    _AntiCaptchaSolver,
    _NoOpSolver,
    _TwoCaptchaSolver,
    get_captcha_solver,
    reset_captcha_solver,
)


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
