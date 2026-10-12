"""CAPTCHA solver adapter — protocol, adapters, and factory.

DataForge does not solve CAPTCHA challenges. Historical third-party adapters
remain private compatibility code, but the factory always returns the no-op
implementation and protected-page recovery always fails closed.

Design constraint
-----------------
This module must not submit challenges, obtain solver tokens, or inject
challenge cookies. See the P0 safety rules in AGENTS.md for the product
boundary.

Historical adapter protocol
---------------------------

The private legacy adapters implement:

============  ======================================================
Method        Purpose
============  ======================================================
``solve()``   Submit the CAPTCHA for solving, return the token
              (or ``None`` on failure / timeout).
``healthcheck()``  Return ``True`` if the solver service is reachable.
============  ======================================================

Factory
-------

:func:`get_captcha_solver` returns a singleton :class:`_NoOpSolver`, regardless
of ``settings.CAPTCHA_PROVIDER``, API keys, or enablement flags. The product
runtime never reaches the historical adapters.

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
            from app.url_safety import get_safe_async_client

            async with get_safe_async_client(timeout=30.0) as client:
                # Submit
                resp = await client.post(self._SUBMIT_URL, data=submit_params)
                try:
                    resp.raise_for_status()
                    body = resp.json()
                finally:
                    await resp.aclose()
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
                    try:
                        result_resp.raise_for_status()
                        result_body = result_resp.json()
                    finally:
                        await result_resp.aclose()
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
            from app.url_safety import get_safe_async_client

            async with get_safe_async_client(timeout=10.0) as client:
                resp = await client.get(
                    self._RESULT_URL,
                    params={"key": self._api_key, "action": "get", "id": "0", "json": "1"},
                )
                try:
                    return resp.status_code == 200
                finally:
                    await resp.aclose()
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
            from app.url_safety import get_safe_async_client

            async with get_safe_async_client(timeout=30.0) as client:
                resp = await client.post(self._CREATE_URL, json=create_payload)
                try:
                    resp.raise_for_status()
                    body = resp.json()
                finally:
                    await resp.aclose()
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
                    try:
                        result_resp.raise_for_status()
                        result_body = result_resp.json()
                    finally:
                        await result_resp.aclose()
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
            from app.url_safety import get_safe_async_client

            async with get_safe_async_client(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.anti-captcha.com/getBalance",
                    json={"clientKey": self._api_key},
                )
                try:
                    return resp.status_code == 200
                finally:
                    await resp.aclose()
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
    """Return the fail-closed CAPTCHA solver singleton.

    The provider integrations are intentionally unreachable. Configuration
    cannot turn protected-page solving back on in development, staging, or
    production.
    """
    global _solver_instance
    if _solver_instance is not None:
        return _solver_instance

    with _solver_lock:
        if _solver_instance is not None:
            return _solver_instance

        from app.config import settings

        if settings.CAPTCHA_SOLVER_ENABLED or settings.CAPTCHA_API_KEY:
            logger.warning("CAPTCHA solver configuration is ignored; protected pages fail closed")
        _solver_instance = _NoOpSolver()
        return _solver_instance


def reset_captcha_solver() -> None:
    """Reset the singleton solver (for testing)."""
    global _solver_instance
    _solver_instance = None
