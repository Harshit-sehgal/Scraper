"""CAPTCHA solver adapter — protocol, adapters, and factory.

DataForge integrates with third-party CAPTCHA solving services
(2Captcha, Anti-Captcha) to automatically solve challenges that
block extraction.  The solving pipeline is feature-flagged and
off by default — when ``CAPTCHA_SOLVER_ENABLED`` is ``False``
(the default), the :class:`_NoOpSolver` stub is returned and
every ``solve()`` call returns ``None`` so the recovery path
gracefully falls through to proxy rotation + backoff.

Protocol
--------

Every solver must implement:

============  ======================================================
Method        Purpose
============  ======================================================
``solve()``   Submit the CAPTCHA for solving, return the token
              (or ``None`` on failure / timeout).
``healthcheck()``  Return ``True`` if the solver service is reachable.
============  ======================================================

Factory
-------

:func:`get_captcha_solver` returns a singleton based on
``settings.CAPTCHA_PROVIDER`` (``"2captcha"`` or ``"anticaptcha"``).
When ``CAPTCHA_SOLVER_ENABLED`` is ``False``, the factory returns
:class:`_NoOpSolver` regardless of the provider name.

Adapters
--------

- :class:`_TwoCaptchaSolver` — 2Captcha.com API
- :class:`_AntiCaptchaSolver` — Anti-Captcha.com API
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton for :func:`get_captcha_solver`.
_solver_instance: CaptchaSolver | None = None
_solver_lock = __import__("threading").Lock()


class CaptchaSolver:
    """Protocol for CAPTCHA solving services.

    Implementations submit a CAPTCHA challenge to a third-party
    solver and return the solved token, or ``None`` on failure.
    """

    async def solve(
        self,
        *,
        site_key: str,
        page_url: str,
        captcha_type: str = "recaptcha",
    ) -> str | None:
        """Submit a CAPTCHA for solving.

        Parameters
        ----------
        site_key:
            The ``data-sitekey`` attribute from the target page.
        page_url:
            The URL of the page that contains the CAPTCHA.
        captcha_type:
            One of ``"recaptcha"``, ``"hcaptcha"``, ``"turnstile"``.

        Returns
        -------
        The solved token string, or ``None`` on failure/timeout.
        """
        return None

    async def healthcheck(self) -> bool:
        """Return ``True`` if the solver service is reachable."""
        return False


class _NoOpSolver(CaptchaSolver):
    """No-op solver returned when CAPTCHA solving is disabled.

    Every ``solve()`` call returns ``None`` and ``healthcheck()``
    returns ``False``.  This is the default when
    ``CAPTCHA_SOLVER_ENABLED=False`` so the recovery escalation
    path falls through gracefully.
    """

    async def solve(
        self,
        *,
        site_key: str,
        page_url: str,
        captcha_type: str = "recaptcha",
    ) -> str | None:
        logger.debug("CAPTCHA solver disabled; returning None")
        return None

    async def healthcheck(self) -> bool:
        return False


class _TwoCaptchaSolver(CaptchaSolver):
    """2Captcha.com API adapter.

    POSTs the site key + page URL to ``2captcha.com/in.php``, then
    polls ``2captcha.com/res.php`` every 5 s up to
    ``settings.CAPTCHA_SOLVE_TIMEOUT_S``.
    """

    _SUBMIT_URL = "https://2captcha.com/in.php"
    _RESULT_URL = "https://2captcha.com/res.php"
    _POLL_INTERVAL = 5.0

    def __init__(self, api_key: str, *, timeout_s: int = 120) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def solve(
        self,
        *,
        site_key: str,
        page_url: str,
        captcha_type: str = "recaptcha",
    ) -> str | None:
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available; cannot submit CAPTCHA to 2Captcha")
            return None

        method = self._map_method(captcha_type)
        submit_params: dict[str, str] = {
            "key": self._api_key,
            "method": method,
            "googlekey": site_key,
            "pageurl": page_url,
            "json": "1",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Submit
                resp = await client.post(self._SUBMIT_URL, data=submit_params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("status") != 1:
                    logger.warning("2Captcha submit error: %s", body.get("request", "unknown"))
                    return None
                task_id = body["request"]

                # Poll for result
                elapsed = 0.0
                while elapsed < self._timeout_s:
                    await asyncio.sleep(self._POLL_INTERVAL)
                    elapsed += self._POLL_INTERVAL
                    result_resp = await client.get(
                        self._RESULT_URL,
                        params={
                            "key": self._api_key,
                            "action": "get",
                            "id": task_id,
                            "json": "1",
                        },
                    )
                    result_resp.raise_for_status()
                    result_body = result_resp.json()
                    if result_body.get("status") == 1:
                        return result_body["request"]
                    if result_body.get("request") != "CAPCHA_NOT_READY":
                        logger.warning("2Captcha result error: %s", result_body.get("request"))
                        return None

                logger.warning("2Captcha solve timed out after %ds", self._timeout_s)
                return None

        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("2Captcha solve failed: %s", exc)
            return None

    async def healthcheck(self) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    self._RESULT_URL,
                    params={"key": self._api_key, "action": "get", "id": "0", "json": "1"},
                )
                return resp.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    @staticmethod
    def _map_method(captcha_type: str) -> str:
        mapping = {"recaptcha": "userrecaptcha", "hcaptcha": "hcaptcha", "turnstile": "turnstile"}
        return mapping.get(captcha_type, "userrecaptcha")


class _AntiCaptchaSolver(CaptchaSolver):
    """Anti-Captcha.com API adapter.

    Creates a task via ``/createTask``, then polls ``/getTaskResult``
    every 5 s up to ``settings.CAPTCHA_SOLVE_TIMEOUT_S``.
    """

    _CREATE_URL = "https://api.anti-captcha.com/createTask"
    _RESULT_URL = "https://api.anti-captcha.com/getTaskResult"
    _POLL_INTERVAL = 5.0

    def __init__(self, api_key: str, *, timeout_s: int = 120) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def solve(
        self,
        *,
        site_key: str,
        page_url: str,
        captcha_type: str = "recaptcha",
    ) -> str | None:
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available; cannot submit CAPTCHA to Anti-Captcha")
            return None

        task_type = self._map_task_type(captcha_type)
        create_payload: dict[str, Any] = {
            "clientKey": self._api_key,
            "task": {
                "type": task_type,
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self._CREATE_URL, json=create_payload)
                resp.raise_for_status()
                body = resp.json()
                if body.get("errorId", 0) != 0:
                    logger.warning("Anti-Captcha createTask error: %s", body.get("errorDescription", "unknown"))
                    return None
                task_id = body["taskId"]

                # Poll for result
                elapsed = 0.0
                while elapsed < self._timeout_s:
                    await asyncio.sleep(self._POLL_INTERVAL)
                    elapsed += self._POLL_INTERVAL
                    result_resp = await client.post(
                        self._RESULT_URL,
                        json={"clientKey": self._api_key, "taskId": task_id},
                    )
                    result_resp.raise_for_status()
                    result_body = result_resp.json()
                    if result_body.get("status") == "ready":
                        return result_body.get("solution", {}).get("gRecaptchaResponse") or result_body.get("solution", {}).get(
                            "token"
                        )
                    if result_body.get("errorId", 0) != 0:
                        logger.warning(
                            "Anti-Captcha getTaskResult error: %s",
                            result_body.get("errorDescription", "unknown"),
                        )
                        return None

                logger.warning("Anti-Captcha solve timed out after %ds", self._timeout_s)
                return None

        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Anti-Captcha solve failed: %s", exc)
            return None

    async def healthcheck(self) -> bool:
        try:
            import httpx
        except ImportError:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.anti-captcha.com/getBalance",
                    json={"clientKey": self._api_key},
                )
                return resp.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    @staticmethod
    def _map_task_type(captcha_type: str) -> str:
        mapping = {
            "recaptcha": "NoCaptchaTaskProxyless",
            "hcaptcha": "HCaptchaTaskProxyless",
            "turnstile": "TurnstileTaskProxyless",
        }
        return mapping.get(captcha_type, "NoCaptchaTaskProxyless")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_captcha_solver() -> CaptchaSolver:
    """Return the singleton CAPTCHA solver based on settings.

    When ``CAPTCHA_SOLVER_ENABLED`` is ``False`` (default), returns
    a :class:`_NoOpSolver`.  When enabled, returns the appropriate
    adapter based on ``CAPTCHA_PROVIDER`` (``"2captcha"`` or
    ``"anticaptcha"``).
    """
    global _solver_instance
    if _solver_instance is not None:
        return _solver_instance

    with _solver_lock:
        if _solver_instance is not None:
            return _solver_instance

        from app.config import settings

        if not settings.CAPTCHA_SOLVER_ENABLED:
            _solver_instance = _NoOpSolver()
            return _solver_instance

        provider = (settings.CAPTCHA_PROVIDER or "2captcha").strip().lower()
        api_key = settings.CAPTCHA_API_KEY or ""
        timeout = settings.CAPTCHA_SOLVE_TIMEOUT_S

        if not api_key:
            logger.warning("CAPTCHA_SOLVER_ENABLED=True but CAPTCHA_API_KEY is empty; using NoOp")
            _solver_instance = _NoOpSolver()
            return _solver_instance

        if provider == "2captcha":
            _solver_instance = _TwoCaptchaSolver(api_key, timeout_s=timeout)
            logger.info("Using _TwoCaptchaSolver")
        elif provider == "anticaptcha":
            _solver_instance = _AntiCaptchaSolver(api_key, timeout_s=timeout)
            logger.info("Using _AntiCaptchaSolver")
        else:
            logger.warning("Unknown CAPTCHA_PROVIDER=%r; using NoOp", provider)
            _solver_instance = _NoOpSolver()

        return _solver_instance


def reset_captcha_solver() -> None:
    """Reset the singleton solver (for testing)."""
    global _solver_instance
    _solver_instance = None
