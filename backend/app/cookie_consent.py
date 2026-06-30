"""Cookie Consent Handler — detect and dismiss common cookie consent banners.

Detects cookie consent banners from popular frameworks (Cookiebot,
OneTrust, Osano, Quantcast Choice, iubenda, Didomi, TrustArc, etc.)
and handles them according to a configurable policy (accept_all,
reject_all, dismiss_only).

This runs inside the browser page context after navigation, before
extraction begins, so consent dialogs don't block content rendering.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection selectors for 10+ common cookie consent frameworks
# ---------------------------------------------------------------------------

_FRAMEWORK_DETECTORS: list[dict[str, Any]] = [
    # Cookiebot
    {
        "framework": "Cookiebot",
        "detect_selector": "#CybotCookiebotDialog, .Cookiebot",
        "accept_selector": "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, #CybotCookiebotDialogBodyButtonAccept",
        "reject_selector": "#CybotCookiebotDialogBodyLevelButtonLevelOptinDecline, #CybotCookiebotDialogBodyButtonDecline",
    },
    # OneTrust
    {
        "framework": "OneTrust",
        "detect_selector": "#onetrust-accept-btn-handler, #onetrust-banner-sdk, .onetrust-persistent-dark",
        "accept_selector": "#onetrust-accept-btn-handler, .onetrust-close-btn-handler",
        "reject_selector": "#onetrust-reject-all-handler, .onetrust-pc-btn-handler",
    },
    # Osano
    {
        "framework": "Osano",
        "detect_selector": ".osano-cm-dialog, .osano-cm-window",
        "accept_selector": ".osano-cm-accept-all, .osano-cm-accept",
        "reject_selector": ".osano-cm-denyAll, .osano-cm-deny",
    },
    # Quantcast Choice
    {
        "framework": "QuantcastChoice",
        "detect_selector": ".qc-cmp2-container, .qc-cmp-button",
        "accept_selector": ".qc-cmp2-buttons-desktop button:first-child, .qc-cmp-button:nth-child(1)",
        "reject_selector": ".qc-cmp2-buttons-desktop button:last-child",
    },
    # iubenda
    {
        "framework": "iubenda",
        "detect_selector": "#iubenda-cs-banner, .iubenda-cs-banner",
        "accept_selector": ".iubenda-cs-accept-btn, #iubenda-cs-accept-btn",
        "reject_selector": ".iubenda-cs-reject-btn",
    },
    # Didomi
    {
        "framework": "Didomi",
        "detect_selector": ".didomi-popup-container, #didomi-popup",
        "accept_selector": ".didomi-popup-accept-all, .didomi-accept-all-btn",
        "reject_selector": ".didomi-popup-disagree-all, .didomi-disagree-all-btn",
    },
    {
        "framework": "TrustArc",
        "detect_selector": "#truste-consent-track, .truste-consent-track",
        "accept_selector": ".truste-consent-button, .truste-button1",
        "reject_selector": ".truste-consent-required-reject, .truste-button3",
    },
    # Civic Cookie Control
    {
        "framework": "CivicCookieControl",
        "detect_selector": ".ccc-wr, .ccc-overlay",
        "accept_selector": ".ccc-accept, .ccc-accept-all",
        "reject_selector": ".ccc-reject, .ccc-reject-all",
    },
    # Generic / fallback patterns
    {
        "framework": "GenericAccept",
        "detect_selector": (
            '[data-testid="cookie-banner"], [class*="cookie-banner"], '
            '[class*="CookieBanner"], [id*="cookie-banner"], '
            '[class*="consent-banner"], [class*="gdpr-banner"]'
        ),
        "accept_selector": (
            'button:has-text("Accept All"), button:has-text("Accept"), '
            'button:has-text("Accept all"), button:has-text("OK"), '
            'button:has-text("Got it"), button:has-text("I agree"), '
            'a:has-text("Accept"), a:has-text("OK")'
        ),
        "reject_selector": (
            'button:has-text("Reject All"), button:has-text("Reject"), '
            'button:has-text("Necessary Only"), button:has-text("Only necessary"), '
            'button:has-text("Decline"), button:has-text("Opt out")'
        ),
    },
    # CMP-specific: CookieLawInfo / GDPR Cookie Consent
    {
        "framework": "CookieLawInfo",
        "detect_selector": "#cookie-law-info-bar, .cookie-law-info-bar, .cli-bar-container",
        "accept_selector": "#cookie_action_accept, .cli-user-accept-button, .wt-cli-accept-btn",
        "reject_selector": "#cookie_action_reject, .cli-user-reject-button",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def detect_cookie_banner(page: Any) -> dict[str, Any] | None:
    """Detect a cookie consent banner on the current page.

    Returns a dict with ``framework``, ``detect_selector``, and
    available ``accept_selector`` / ``reject_selector``, or ``None``
    if no banner is detected.
    """
    for detector in _FRAMEWORK_DETECTORS:
        selector = detector["detect_selector"]
        try:
            # Check multiple selectors (comma-separated)
            for single_sel in selector.split(","):
                single_sel = single_sel.strip()
                if not single_sel:
                    continue
                visible = await page.locator(single_sel).first.is_visible()
                if visible:
                    return {
                        "framework": detector["framework"],
                        "detect_selector": single_sel,
                        "accept_selector": detector.get("accept_selector", ""),
                        "reject_selector": detector.get("reject_selector", ""),
                    }
        except (RuntimeError, OSError, ValueError, TimeoutError):
            # Page might be navigating or element detached
            continue
    return None


async def handle_cookie_consent(
    page: Any,
    *,
    policy: str = "accept_all",
    timeout_ms: int = 3000,
) -> bool:
    """Handle cookie consent banner according to *policy*.

    Args:
        page: Playwright page object.
        policy: One of ``accept_all``, ``reject_all``, ``dismiss_only``.
        timeout_ms: Maximum wait time for button visibility per selector.

    Returns:
        ``True`` if a banner was found and handled, ``False`` otherwise.
    """
    banner = await detect_cookie_banner(page)
    if banner is None:
        return False

    framework = banner["framework"]
    logger.info("Detected cookie consent banner (%s), policy=%s", framework, policy)

    action_selector = banner.get("reject_selector", "") if policy == "reject_all" else banner.get("accept_selector", "")

    if not action_selector:
        logger.warning("No %s selector available for %s, skipping", policy, framework)
        return False

    # Try each comma-separated selector
    for single_sel in action_selector.split(","):
        single_sel = single_sel.strip()
        if not single_sel:
            continue
        try:
            locator = page.locator(single_sel).first
            if await locator.is_visible(timeout=timeout_ms):
                await locator.click(timeout=timeout_ms)
                logger.info("Clicked %s button via %s for %s", policy, single_sel, framework)
                # Brief wait for banner dismiss animation
                await asyncio.sleep(0.5)
                return True
        except (RuntimeError, OSError, ValueError, TimeoutError):
            continue

    logger.warning("Could not click %s button for %s-banner", policy, framework)
    return False
