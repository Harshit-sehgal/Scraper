"""Failure Explainer — user-friendly explanations for extraction failures.

Maps technical failure signals to actionable user messages.
Supports the full failure taxonomy from the Prompt 11 spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FailureExplanation:
    """Structured failure explanation for users."""

    failure_type: str
    user_message: str
    technical_details: str
    recommended_action: str
    screenshot_available: bool = False
    timeline: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

_FAILURE_MAP = {
    "login_required": {
        "user_message": "This page requires a login. Please create an Auth Profile to access it.",
        "technical_details": "The target page returned a login form or redirect to an authentication endpoint.",
        "recommended_action": "Create an Auth Profile: go to Auth Profiles, click 'Create', enter the domain, and complete the login flow.",
    },
    "session_expired": {
        "user_message": "Your session for this website has expired. Please reconnect this Auth Profile.",
        "technical_details": "The stored session cookies are no longer valid. The site returned a session-expired indicator.",
        "recommended_action": "Go to Auth Profiles, find the expired profile, and click 'Reconnect' to refresh the session.",
    },
    "session_url": {
        "user_message": "This URL appears to use a temporary session. Direct scraping may not work reliably.",
        "technical_details": "The URL contains session-bound parameters (e.g., searchId, sid, token) that may expire quickly.",
        "recommended_action": "Use Workflow Replay to create a reliable scraping workflow that navigates from the main page.",
    },
    "selector_not_found": {
        "user_message": "The page structure has changed and the expected data cannot be found.",
        "technical_details": "Configured CSS selectors or heuristics did not match any elements on the page.",
        "recommended_action": "Use the URL Analyzer to re-detect fields, or manually update the selector mapping in the workflow.",
    },
    "blocked_or_challenge": {
        "user_message": "The website is showing a challenge or blocking automated access.",
        "technical_details": "Anti-bot signals detected: CAPTCHA, rate-limit response, or bot challenge page.",
        "recommended_action": "Pause and retry later, reduce request frequency, or request permission from the site owner.",
    },
    "timeout": {
        "user_message": "The page took too long to load.",
        "technical_details": "The request exceeded the configured timeout threshold.",
        "recommended_action": "Increase the wait timeout in the job settings, or reduce the scope of the extraction (fewer pages).",
    },
    "network_error": {
        "user_message": "Could not reach the website.",
        "technical_details": "DNS resolution failed, connection refused, or HTTP error.",
        "recommended_action": "Check that the URL is correct and the website is accessible. Try again later.",
    },
    "no_records_found": {
        "user_message": "No data records were found on this page.",
        "technical_details": "The extraction ran successfully but produced zero records.",
        "recommended_action": "Verify the URL and selectors. The page may be empty or the data may be loaded dynamically.",
    },
    "quota_exceeded": {
        "user_message": "You have reached your usage limit for this plan.",
        "technical_details": "Quota check returned over-limit for the current billing period.",
        "recommended_action": "Upgrade your plan or wait until the next billing period.",
    },
    "domain_blocked": {
        "user_message": "This website is not allowed for scraping.",
        "technical_details": "The URL safety check rejected the domain as unsafe or against acceptable use policy.",
        "recommended_action": "Review the Acceptable Use Policy. If you believe this is an error, contact support.",
    },
    "auth_profile_revoked": {
        "user_message": "The Auth Profile used for this job has been revoked.",
        "technical_details": "The auth profile status is 'revoked' or the encrypted storage state has been cleared.",
        "recommended_action": "Create a new Auth Profile for this domain and re-run the job.",
    },
    "auth_profile_expired": {
        "user_message": "The Auth Profile used for this job has expired.",
        "technical_details": "The auth profile status is 'expired' or the session has timed out.",
        "recommended_action": "Reconnect the Auth Profile or create a new one.",
    },
    "unknown_error": {
        "user_message": "An unexpected error occurred during extraction.",
        "technical_details": "An unhandled exception was raised during the extraction pipeline.",
        "recommended_action": "Try again. If the issue persists, check the logs or contact support.",
    },
}


# ---------------------------------------------------------------------------
# Detection heuristics
# ---------------------------------------------------------------------------


def detect_failure(
    *,
    http_status: int | None = None,
    page_text: str | None = None,
    redirect_url: str | None = None,
    selector_found: bool = True,
    records_found: int = 0,
    has_auth_profile: bool = False,
    auth_profile_status: str | None = None,
    quota_status: str | None = None,
    url_safety_result: str | None = None,
    exception_type: str | None = None,
    timeout_occurred: bool = False,
) -> FailureExplanation:
    """Detect the type of failure from available signals.

    Args:
        http_status: HTTP status code if available
        page_text: Visible page text for text-based detection
        redirect_url: URL after any redirects
        selector_found: Whether the expected selector was found
        records_found: Number of records extracted
        has_auth_profile: Whether an auth profile was used
        auth_profile_status: Status of the auth profile
        quota_status: Quota check result
        url_safety_result: URL safety check result
        exception_type: Type of exception if any
        timeout_occurred: Whether a timeout occurred

    Returns:
        FailureExplanation with user-friendly details.
    """
    failure_type = "unknown_error"

    # Priority order matters
    if timeout_occurred:
        failure_type = "timeout"
    elif url_safety_result == "blocked":
        failure_type = "domain_blocked"
    elif quota_status == "exceeded":
        failure_type = "quota_exceeded"
    elif has_auth_profile and auth_profile_status == "revoked":
        failure_type = "auth_profile_revoked"
    elif has_auth_profile and auth_profile_status == "expired":
        failure_type = "auth_profile_expired"
    elif http_status in (401, 403):
        failure_type = "session_expired" if has_auth_profile else "login_required"
    elif http_status in (301, 302, 307, 308) and redirect_url:
        # Check if redirect is to a login page
        if page_text and any(kw in page_text.lower() for kw in ("login", "sign in", "log in", "authentication")):
            failure_type = "login_required"
    elif not selector_found:
        failure_type = "selector_not_found"
    elif records_found == 0:
        failure_type = "no_records_found"
    elif exception_type and "timeout" in exception_type.lower():
        failure_type = "timeout"
    elif exception_type and "blocked" in exception_type.lower():
        failure_type = "blocked_or_challenge"

    return explain_failure(failure_type)


def explain_failure(failure_type: str) -> FailureExplanation:
    """Return a FailureExplanation for the given failure type.

    Args:
        failure_type: One of the known failure type strings.

    Returns:
        FailureExplanation with user-friendly message and action.
    """
    info = _FAILURE_MAP.get(failure_type, _FAILURE_MAP["unknown_error"])
    if failure_type not in _FAILURE_MAP:
        failure_type = "unknown_error"
    return FailureExplanation(
        failure_type=failure_type,
        user_message=info["user_message"],
        technical_details=info["technical_details"],
        recommended_action=info["recommended_action"],
        timeline=None,
    )


def classify_error(error: Exception) -> str:
    """Classify an exception into a failure type string.

    Args:
        error: The exception to classify.

    Returns:
        A failure type string.
    """
    error_str = str(error).lower()
    exc_type = type(error).__name__.lower()

    if "timeout" in exc_type or "timeout" in error_str:
        return "timeout"
    if "redirect" in error_str:
        return "session_url"
    if "403" in error_str or "401" in error_str or "unauthorized" in error_str:
        return "login_required"
    if "captcha" in error_str or "challenge" in error_str or "blocked" in error_str:
        return "blocked_or_challenge"
    if "quota" in error_str or "rate limit" in error_str:
        return "quota_exceeded"
    if "dns" in error_str or "connection" in error_str:
        return "network_error"
    return "unknown_error"
