"""Cloudflare ``cf_clearance`` cookie harvester loop.

When a Cloudflare challenge page is detected, the anti-bot recovery
pipeline can invoke :func:`harvest_cf_clearance` to open a dedicated
Playwright context, navigate to the challenge page, wait for the JS
challenge to auto-resolve, and capture the resulting ``cf_clearance``
cookie.  The captured cookie is persisted to
:class:`~app.anti_bot_engine.AntiBotEngine` and the browser pool
subsequently injects it into every fresh context for that domain.

Feature flag
------------

``settings.CF_HARVESTER_ENABLED`` defaults to ``False``.  When the
flag is off, :func:`harvest_cf_clearance` short-circuits and returns
``None`` so the recovery pipeline escalates to backoff/abort quickly
without burning a browser context.  Operators enable the harvester
deliberately by setting ``DATAFORGE_CF_HARVESTER_ENABLED=true``.

Safety
------

- The function opens an **isolated** browser context via
  :meth:`~app.browser_pool.BrowserPool.acquire_context` so it does
  not interfere with the in-progress scraping context.
- Semaphore release is guaranteed by the ``finally`` block on the
  acquired context.
- The function never raises; all exceptions are logged and converted
  to ``None`` so callers can treat a return value of ``None`` as
  "harvest unsuccessful, escalate to next recovery step".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_cookie_header_from_dict(cookies: list[dict[str, Any]]) -> str:
    """Render a Playwright-style ``[{name, value, ...}, ...]`` cookie list
    into an HTTP Cookie header compatible with ``httpx`` / ``requests``.

    Only ``name`` and ``value`` are used; ``domain``, ``path``, etc.
    are irrelevant for header transport.
    """
    pairs: list[str] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if isinstance(name, str) and value is not None:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


async def harvest_cf_clearance(
    url: str,
    domain: str,
    *,
    timeout_s: float | None = None,
    max_render_wait_s: float | None = None,
) -> str | None:
    """Harvest the ``cf_clearance`` cookie from a Cloudflare challenge page.

    Parameters
    ----------
    url : str
        Full URL of the challenge page.
    domain : str
        Domain the cookie should be persisted under.
    timeout_s : float, optional
        Total seconds to wait for the cookie to appear.  Defaults to
        ``settings.CF_HARVESTER_TIMEOUT_S`` (30.0).
    max_render_wait_s : float, optional
        Seconds to wait for the page to render before polling for
        cookies.  Defaults to ``settings.CF_HARVESTER_MAX_RENDER_WAIT_S``
        (15.0).

    Returns
    -------
    str | None
        The ``Cookie: cf_clearance=...`` header string on success,
        ``None`` if the feature is disabled, the cookie did not
        appear within ``timeout_s``, or any error occurred.

    Side effects
    ------------
    On success, the cookie is persisted via
    :meth:`app.anti_bot_engine.AntiBotEngine.update_cookies` and
    :func:`app.metrics_collector.record_cf_harvest_attempt` is
    invoked with ``success=True``.  On failure, ``success=False``.
    """
    from app.config import settings

    if not getattr(settings, "CF_HARVESTER_ENABLED", False):
        logger.debug("CF harvester disabled; skipping")
        return None

    actual_timeout = timeout_s if timeout_s is not None else settings.CF_HARVESTER_TIMEOUT_S
    actual_render_wait = max_render_wait_s if max_render_wait_s is not None else settings.CF_HARVESTER_MAX_RENDER_WAIT_S

    pool = None
    context = None
    try:
        from app.browser_pool import get_browser_pool

        pool = get_browser_pool()
    except ImportError:
        logger.debug("BrowserPool not available; CF harvester cannot run")
        return None

    if pool is None:
        return None

    try:
        acquire = getattr(pool, "acquire_context", None)
        if acquire is None:
            logger.debug("BrowserPool.acquire_context not found")
            return None

        context = await acquire(url=url, domain=domain)

        page = await context.new_page()
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=int(actual_render_wait * 1000))
            except (TimeoutError, KeyError, ValueError, OSError) as exc:
                logger.debug("CF harvester initial render failure (expected for challenges): %s", exc)

            # Poll cookies every second up to actual_timeout seconds
            elapsed = 0.0
            poll_interval = 1.0
            clearance_value: str | None = None
            while elapsed < actual_timeout:
                cookies = await context.cookies()
                if cookies:
                    for c in cookies:
                        if c.get("name") == "cf_clearance":
                            clearance_value = str(c.get("value", ""))
                            break
                if clearance_value:
                    break
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            if not clearance_value:
                try:
                    from app.metrics_collector import record_cf_harvest_attempt

                    record_cf_harvest_attempt(success=False)
                except (ImportError, AttributeError, TypeError):
                    pass
                logger.info("CF harvester timed out for %s after %.1fs (no cf_clearance)", domain, actual_timeout)
                return None

            # Build cookie header for the full browser cookie jar
            cookies = await context.cookies()
            cookie_header = build_cookie_header_from_dict(cookies)

            try:
                from app.anti_bot_engine import get_anti_bot_engine

                get_anti_bot_engine().update_cookies(domain, cookie_header)
            except (ImportError, AttributeError, RuntimeError, ValueError, TypeError) as exc:
                logger.warning("CF harvester cookie persist failed: %s", exc)

            try:
                from app.metrics_collector import record_cf_harvest_attempt

                record_cf_harvest_attempt(success=True)
            except (ImportError, AttributeError, TypeError):
                pass

            logger.info("CF harvester captured cf_clearance for %s", domain)
            return cookie_header
        finally:
            # M8: always close the page — prevents Playwright memory leak
            # when the polling loop exits early or the outer handler fails.
            try:
                await page.close()
            except (RuntimeError, OSError, ValueError):
                logger.debug("CF harvester page.close() failed (ignored)")

    except (ImportError, AttributeError, RuntimeError, ValueError, TypeError, OSError) as exc:
        try:
            from app.metrics_collector import record_cf_harvest_attempt

            record_cf_harvest_attempt(success=False)
        except (ImportError, AttributeError, TypeError):
            pass
        logger.warning("CF harvester failed for %s: %s", domain, exc)
        return None
    finally:
        # Release the acquired context if the pool exposes a release helper.
        release = getattr(pool, "release_context", None) if pool is not None else None
        if context is not None and callable(release):
            try:
                result = release(context)
                if hasattr(result, "__await__"):
                    await result  # type: ignore[func-returns-value]
            except (RuntimeError, ValueError, TypeError, OSError):
                pass
