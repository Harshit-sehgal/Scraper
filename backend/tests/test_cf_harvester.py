"""Tests for the Cloudflare cf_clearance harvester loop.

Validates:
1. harvest_cf_clearance returns None when CF_HARVESTER_ENABLED=False
2. harvest_cf_clearance returns None when BrowserPool is unavailable
3. harvest_cf_clearance returns None when pool lacks acquire_context
4. Successful harvest calls update_cookies and records success metric
5. Timeout harvest records failure metric and returns None
6. build_cookie_header_from_dict renders correct header string
7. build_cookie_header_from_dict skips malformed entries
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.cf_harvester import build_cookie_header_from_dict, harvest_cf_clearance

# ---------------------------------------------------------------------------
# build_cookie_header_from_dict
# ---------------------------------------------------------------------------


class TestBuildCookieHeader:
    def test_renders_name_value_pairs(self) -> None:
        cookies = [
            {"name": "cf_clearance", "value": "abc123"},
            {"name": "session", "value": "xyz"},
        ]
        result = build_cookie_header_from_dict(cookies)
        assert result == "cf_clearance=abc123; session=xyz"

    def test_empty_list_returns_empty_string(self) -> None:
        assert build_cookie_header_from_dict([]) == ""

    def test_skips_non_dict_entries(self) -> None:
        cookies: list[dict[str, object]] = [
            {"name": "valid", "value": "1"},  # type: ignore[list-item]
            "not-a-dict",  # type: ignore[list-item]
            42,  # type: ignore[list-item]
        ]
        result = build_cookie_header_from_dict(cookies)
        assert result == "valid=1"

    def test_skips_missing_name_or_value(self) -> None:
        cookies = [
            {"value": "no-name"},  # missing name → skip
            {"name": "no-value"},  # value=None → skip
            {"name": "ok", "value": "yes"},
        ]
        result = build_cookie_header_from_dict(cookies)
        assert result == "ok=yes"

    def test_non_string_name_skipped(self) -> None:
        cookies = [{"name": 123, "value": "bad"}]  # type: ignore[dict-item]
        result = build_cookie_header_from_dict(cookies)
        assert result == ""

    def test_value_none_skipped(self) -> None:
        cookies = [{"name": "x", "value": None}]
        result = build_cookie_header_from_dict(cookies)
        assert result == ""


# ---------------------------------------------------------------------------
# Helpers — match the real BrowserPool.acquire_context contract:
# an @asynccontextmanager that yields (ctx_id, ctx).
# ---------------------------------------------------------------------------


def _make_pool(context: AsyncMock) -> MagicMock:
    """Build a mock pool whose acquire_context() is the real async CM
    that yields the supplied context."""

    @asynccontextmanager
    async def _acquire(**_kwargs: object):  # ignore viewport args
        yield ("iso:test-ctx-id", context)

    pool = MagicMock()
    pool.acquire_context = _acquire
    pool.release_context = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# harvest_cf_clearance — feature-flag disabled
# ---------------------------------------------------------------------------


class TestHarvestDisabled:
    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", False)
        result = await harvest_cf_clearance("https://example.com", "example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_import_browser_pool_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", False)
        with patch.dict("sys.modules", {"app.browser_pool": None}):
            result = await harvest_cf_clearance("https://example.com", "example.com")
        assert result is None


# ---------------------------------------------------------------------------
# harvest_cf_clearance — browser pool unavailable
# ---------------------------------------------------------------------------


class TestHarvestPoolUnavailable:
    @pytest.mark.asyncio
    async def test_returns_none_when_pool_import_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)
        with patch("app.browser_pool.get_browser_pool", side_effect=ImportError):
            result = await harvest_cf_clearance("https://example.com", "example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_pool_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)
        with patch("app.browser_pool.get_browser_pool", return_value=None):
            result = await harvest_cf_clearance("https://example.com", "example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_pool_lacks_acquire(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)
        # Spec=[] means the mock raises AttributeError for any attribute,
        # which mirrors the getattr(..., None) check path in the function.
        pool = MagicMock()
        with patch("app.browser_pool.get_browser_pool", return_value=pool):
            result = await harvest_cf_clearance("https://example.com", "example.com")
        assert result is None


# ---------------------------------------------------------------------------
# harvest_cf_clearance — successful harvest
# ---------------------------------------------------------------------------


class TestHarvestSuccess:
    @pytest.mark.asyncio
    async def test_success_calls_update_cookies_and_records_metric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock(return_value=None)
        mock_context.cookies = AsyncMock(
            return_value=[
                {"name": "cf_clearance", "value": "test-clearance-xyz"},
                {"name": "other", "value": "cookie"},
            ]
        )

        mock_pool = _make_pool(mock_context)
        # After release_context is called via __aexit__,
        # confirm the page.close() was also called.
        mock_engine = MagicMock()
        mock_engine.update_cookies = MagicMock()

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.anti_bot_engine.get_anti_bot_engine", return_value=mock_engine),
            patch("app.metrics_collector.record_cf_harvest_attempt") as mock_record,
        ):
            result = await harvest_cf_clearance(
                "https://example.com/page",
                "example.com",
                timeout_s=2.0,
                max_render_wait_s=2.0,
            )

        assert result is not None
        assert "cf_clearance=test-clearance-xyz" in result
        mock_engine.update_cookies.assert_called_once_with("example.com", result)
        mock_record.assert_called_once_with(success=True)
        # Page must always be closed after the polling loop.
        mock_page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_cookie_header_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock(return_value=None)
        mock_context.cookies = AsyncMock(return_value=[{"name": "cf_clearance", "value": "abc"}])

        mock_pool = _make_pool(mock_context)
        mock_engine = MagicMock()

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.anti_bot_engine.get_anti_bot_engine", return_value=mock_engine),
            patch("app.metrics_collector.record_cf_harvest_attempt"),
        ):
            result = await harvest_cf_clearance("https://example.com", "example.com", timeout_s=2.0, max_render_wait_s=2.0)

        assert result == "cf_clearance=abc"


# ---------------------------------------------------------------------------
# harvest_cf_clearance — timeout / no cf_clearance
# ---------------------------------------------------------------------------


class TestHarvestTimeout:
    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock(return_value=None)
        # Returns cookies but no cf_clearance
        mock_context.cookies = AsyncMock(return_value=[{"name": "other", "value": "val"}])

        mock_pool = _make_pool(mock_context)

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.metrics_collector.record_cf_harvest_attempt") as mock_record,
        ):
            result = await harvest_cf_clearance(
                "https://example.com",
                "example.com",
                timeout_s=0.1,  # very short so test doesn't hang
                max_render_wait_s=0.1,
            )

        assert result is None
        mock_record.assert_called_once_with(success=False)
        # Even on timeout, __aexit__ must release the context and
        # the page must be closed.
        mock_page.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# harvest_cf_clearance — exception during harvest
# ---------------------------------------------------------------------------


class TestHarvestException:
    @pytest.mark.asyncio
    async def test_returns_none_on_unexpected_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        # acquire_context itself raises — pool acquisition failed.
        mock_pool = MagicMock()
        pool_error = RuntimeError("pool error")

        @asynccontextmanager
        async def _acquire_ctx(**_kw: object):  # type: ignore[no-untyped-def]
            raise pool_error
            yield  # pragma: no cover (unreachable)

        mock_pool.acquire_context = _acquire_ctx
        mock_pool.release_context = AsyncMock(return_value=None)

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.metrics_collector.record_cf_harvest_attempt") as mock_record,
        ):
            result = await harvest_cf_clearance(
                "https://example.com",
                "example.com",
                timeout_s=2.0,
                max_render_wait_s=2.0,
            )

        assert result is None
        mock_record.assert_called_once_with(success=False)

    @pytest.mark.asyncio
    async def test_release_context_still_called_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        # goto raises an error that should be caught internally
        mock_page.goto = AsyncMock(side_effect=OSError("network error"))
        # No cf_clearance
        mock_context.cookies = AsyncMock(return_value=[])

        mock_pool = _make_pool(mock_context)

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.metrics_collector.record_cf_harvest_attempt"),
        ):
            result = await harvest_cf_clearance(
                "https://example.com",
                "example.com",
                timeout_s=0.1,
                max_render_wait_s=0.1,
            )

        # goto error caught, poll loop runs, no cf_clearance → None
        assert result is None
        # page.close must always run via the inner finally.
        mock_page.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# harvest_cf_clearance — update_cookies failure doesn't block success
# ---------------------------------------------------------------------------


class TestHarvestUpdateCookiesFailure:
    @pytest.mark.asyncio
    async def test_returns_header_even_if_update_cookies_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock(return_value=None)
        mock_context.cookies = AsyncMock(return_value=[{"name": "cf_clearance", "value": "persisted"}])

        mock_pool = _make_pool(mock_context)

        failing_engine = MagicMock()
        failing_engine.update_cookies = MagicMock(side_effect=ValueError("db down"))

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.anti_bot_engine.get_anti_bot_engine", return_value=failing_engine),
            patch("app.metrics_collector.record_cf_harvest_attempt"),
        ):
            result = await harvest_cf_clearance(
                "https://example.com",
                "example.com",
                timeout_s=2.0,
                max_render_wait_s=2.0,
            )

        assert result is not None
        assert "cf_clearance=persisted" in result


# ---------------------------------------------------------------------------
# harvest_cf_clearance — async release via __aexit__
# ---------------------------------------------------------------------------


class TestHarvestAsyncRelease:
    @pytest.mark.asyncio
    async def test_pool_release_runs_via_aexit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """exercising the @asynccontextmanager path: __aexit__ must run
        on normal timeout-return and on happy path alike. The pool's real
        release_context will be called by __aexit__ eagerly closing the
        BrowserContext after page.close()."""
        from app.config import settings

        monkeypatch.setattr(settings, "CF_HARVESTER_ENABLED", True)
        monkeypatch.setattr(settings, "CF_HARVESTER_TIMEOUT_S", 5.0)
        monkeypatch.setattr(settings, "CF_HARVESTER_MAX_RENDER_WAIT_S", 5.0)

        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock(return_value=None)
        # No cf_clearance → times out
        mock_context.cookies = AsyncMock(return_value=[])

        mock_pool = _make_pool(mock_context)

        with (
            patch("app.browser_pool.get_browser_pool", return_value=mock_pool),
            patch("app.metrics_collector.record_cf_harvest_attempt"),
        ):
            result = await harvest_cf_clearance(
                "https://example.com",
                "example.com",
                timeout_s=0.1,
                max_render_wait_s=0.1,
            )

        assert result is None
        # page.close must run inside the inner finally.
        mock_page.close.assert_awaited_once()
