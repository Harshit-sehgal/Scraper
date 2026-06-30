"""Unit tests for cookie_consent.

Covers framework detector count, banner detection with mocked pages,
consent handling with accept_all/reject_all policies, missing-banner
short-circuit, and click-failure resilience.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app import cookie_consent as cc

# ---------------------------------------------------------------------------
# Framework detector integrity
# ---------------------------------------------------------------------------


class TestFrameworkDetectors:
    """_FRAMEWORK_DETECTORS has the expected number of entries."""

    def test_at_least_ten_entries(self) -> None:
        """There must be at least 10 framework detectors."""
        assert len(cc._FRAMEWORK_DETECTORS) >= 10

    def test_each_entry_has_required_keys(self) -> None:
        """Every detector dict must carry framework, detect_selector, accept_selector, reject_selector."""
        for d in cc._FRAMEWORK_DETECTORS:
            assert "framework" in d
            assert "detect_selector" in d
            assert "accept_selector" in d
            assert "reject_selector" in d

    def test_no_empty_selectors(self) -> None:
        """No detector should have empty string selectors."""
        for d in cc._FRAMEWORK_DETECTORS:
            assert d["detect_selector"], f"Empty detect_selector for {d['framework']}"
            assert d["accept_selector"], f"Empty accept_selector for {d['framework']}"


# ---------------------------------------------------------------------------
# detect_cookie_banner
# ---------------------------------------------------------------------------


def _make_page(visible_selectors: list[str] | None = None) -> AsyncMock:
    """Build a mock Playwright page.

    *visible_selectors* lists the CSS selectors that should report
    ``is_visible() == True``. Everything else returns False.
    """
    visible_set = set(visible_selectors or [])

    class _LocatorMock:
        def __init__(self, selector: str) -> None:
            self._selector = selector
            self.first = self

        def is_visible(self, **kw: Any) -> AsyncMock:
            async def _vis(**_kw: Any) -> bool:
                return self._selector in visible_set

            return _vis()

        def click(self, **kw: Any) -> AsyncMock:
            async def _clk(**_kw: Any) -> None:
                _NOT_VISIBLE = "not visible"
                if self._selector not in visible_set:
                    raise RuntimeError(_NOT_VISIBLE)

            return _clk()

    page = AsyncMock()

    def _locator(selector: str) -> _LocatorMock:
        return _LocatorMock(selector)

    page.locator = _locator
    return page


class TestDetectCookieBanner:
    """detect_cookie_banner identifies visible banners."""

    @pytest.mark.asyncio
    async def test_detects_visible_banner(self) -> None:
        """A visible Cookiebot banner is detected."""
        page = _make_page(visible_selectors=["#CybotCookiebotDialog"])
        result = await cc.detect_cookie_banner(page)
        assert result is not None
        assert result["framework"] == "Cookiebot"
        assert result["detect_selector"] == "#CybotCookiebotDialog"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_banner_visible(self) -> None:
        """If no selector is visible, None is returned."""
        page = _make_page(visible_selectors=[])
        result = await cc.detect_cookie_banner(page)
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_during_check_is_suppressed(self) -> None:
        """RuntimeError during visibility check does not propagate."""
        page = AsyncMock()

        _DETACHED = "detached"

        class _BadLocator:
            first = property(lambda self: self)  # type: ignore[assignment]

            @staticmethod
            def is_visible() -> AsyncMock:
                async def _raise(**_kw: Any) -> None:
                    raise RuntimeError(_DETACHED)

                return _raise()

        def _bad_locator(sel: str) -> _BadLocator:
            return _BadLocator()

        page.locator = _bad_locator
        result = await cc.detect_cookie_banner(page)
        assert result is None


# ---------------------------------------------------------------------------
# handle_cookie_consent
# ---------------------------------------------------------------------------


class TestHandleCookieConsent:
    """handle_cookie_consent applies the requested policy."""

    @pytest.mark.asyncio
    async def test_accept_all_policy(self) -> None:
        """accept_all clicks the accept selector."""
        accept_sel = "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"
        detect_sel = "#CybotCookiebotDialog"
        page = _make_page(visible_selectors=[detect_sel, accept_sel])
        result = await cc.handle_cookie_consent(page, policy="accept_all")
        assert result is True

    @pytest.mark.asyncio
    async def test_reject_all_policy(self) -> None:
        """reject_all clicks the reject selector."""
        reject_sel = "#CybotCookiebotDialogBodyLevelButtonLevelOptinDecline"
        detect_sel = "#CybotCookiebotDialog"
        page = _make_page(visible_selectors=[detect_sel, reject_sel])
        result = await cc.handle_cookie_consent(page, policy="reject_all")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_banner(self) -> None:
        """If no banner is detected, returns False without error."""
        page = _make_page(visible_selectors=[])
        result = await cc.handle_cookie_consent(page, policy="accept_all")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_click_failure(self) -> None:
        """When all selectors fail to click, returns False."""
        detect_sel = "#CybotCookiebotDialog"
        page = _make_page(visible_selectors=[detect_sel])

        _CLICK_FAILED = "click failed"

        class _ClickFailLocator:
            def __init__(self, selector: str) -> None:
                self._selector = selector
                self.first = self

            def is_visible(self, **kw: Any) -> AsyncMock:
                async def _vis(**_kw: Any) -> bool:
                    return "Accept" in self._selector or "CybotCookiebotDialogBody" in self._selector

                return _vis()

            def click(self, **kw: Any) -> AsyncMock:
                async def _clk(**_kw: Any) -> None:
                    raise RuntimeError(_CLICK_FAILED)

                return _clk()

        page.locator = _ClickFailLocator

        # Patch asyncio.sleep to avoid real delay
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await cc.handle_cookie_consent(page, policy="accept_all")
        assert result is False

    @pytest.mark.asyncio
    async def test_dismiss_only_returns_false_without_button(self) -> None:
        """dismiss_only with no visible action button returns False."""
        detect_sel = ".osano-cm-dialog"
        page = _make_page(visible_selectors=[detect_sel])
        # dismiss_only uses accept_selector (same as accept_all),
        # but if the accept button is not visible, it returns False.
        result = await cc.handle_cookie_consent(page, policy="dismiss_only")
        assert result is False
