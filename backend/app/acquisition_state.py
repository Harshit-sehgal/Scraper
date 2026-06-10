"""Acquisition state tracking for URL analysis.

Provides structured enums and models to track how a URL was acquired,
what happened during fetch (redirects, session expiry, recovery), and
the provenance of the final data. Replaces scattered dict-based
redirect_info with typed, testable models.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AcquisitionState(StrEnum):
    """Lifecycle states for URL acquisition.

    Tracks the full journey from initial URL request through any
    redirects, session recovery, and final data extraction.
    """

    # URL fetched successfully with no issues
    DIRECT = "direct"

    # URL redirected to a different path on the same domain
    REDIRECTED = "redirected"

    # URL redirected to homepage — likely a shallow redirect
    HOMEPAGE_REDIRECT = "homepage_redirect"

    # URL redirected to a shallow path — session / token likely expired
    SESSION_EXPIRED = "session_expired"

    # Session was expired but recovered via search form submission
    RECOVERED = "recovered"

    # Session expired, form detected, but recovery failed
    RECOVERY_FAILED = "recovery_failed"

    # Session expired, no search form detected on landing page
    NO_SEARCH_FORM = "no_search_form"

    # Session expired, form detected, but no search params provided
    AWAITING_SEARCH_PARAMS = "awaiting_search_params"

    # Page returned 200 but content appears empty / unhelpful
    EMPTY_RESPONSE = "empty_response"

    # Blocked by anti-bot measures
    ANTI_BOT_BLOCKED = "anti_bot_blocked"

    # Generic path change (not clearly session-related)
    PATH_CHANGED = "path_changed"

    # Cross-domain navigation (not flagged as a redirect)
    CROSS_DOMAIN = "cross_domain"

    # Domain in cooldown — skipped due to DomainRuntimePolicy
    DOMAIN_COOLDOWN = "domain_cooldown"


class AcquisitionLineage(BaseModel):
    """Tracks the full provenance of how a URL was acquired and processed.

    Replaces the ad-hoc redirect_info dict with a typed, structured model
    that captures the original URL, final URL, state transitions, and
    recovery details.
    """

    # The URL as originally provided by the user
    original_url: str

    # The URL after all redirects and recovery attempts
    final_url: str

    # Current acquisition state
    state: AcquisitionState = AcquisitionState.DIRECT

    # Human-readable explanation of what happened
    message: str = ""

    # How the page was fetched (playwright_full, httpx_basic,
    # search_form_post, etc.)
    fetch_method: str = ""

    # If recovery was attempted, what method was used
    recovery_method: str | None = None

    # The fresh URL obtained after recovery (if any)
    recovered_url: str | None = None

    # Whether the original URL had session-bound parameters
    session_bound: bool = False

    # Ephemeral query parameters detected in the original URL
    ephemeral_params: list[str] = Field(default_factory=list)

    # User-friendly message with actionable guidance
    user_message: str = ""

    # Evidence-based acquisition quality signals
    data_evidence_score: float = 0.0
    network_payloads_found: int = 0
    forms_detected: int = 0
    containers_detected: int = 0
    anti_bot_score: float = 0.0
    visible_text_length: int = 0
    recommended_next_action: str = ""

    def get_user_message(self) -> str:
        """Generate a user-friendly message with actionable guidance.

        Returns a clear, non-technical explanation of what happened
        and what the user can do about it.
        """
        if self.user_message:
            return self.user_message

        messages = {
            AcquisitionState.DIRECT: "Page loaded successfully.",
            AcquisitionState.DOMAIN_COOLDOWN: (
                "The domain is in cooldown due to recent failures. The URL was skipped to "
                "respect rate limits and avoid anti-bot escalation."
            ),
            AcquisitionState.REDIRECTED: (
                "The URL was redirected from the original to a new location. Data was extracted from the final page."
            ),
            AcquisitionState.HOMEPAGE_REDIRECT: (
                "The URL redirected to the homepage. The original page may have moved or the session may have expired."
            ),
            AcquisitionState.SESSION_EXPIRED: (
                "The session for this URL has expired. The page redirected to a homepage or "
                "landing page instead of showing results."
            ),
            AcquisitionState.RECOVERED: (
                "The expired session was recovered by re-submitting the search form. Fresh results are now available."
            ),
            AcquisitionState.RECOVERY_FAILED: (
                "The session expired and automatic recovery failed. Try providing search parameters to re-fetch the data."
            ),
            AcquisitionState.NO_SEARCH_FORM: (
                "The session expired and no search form was found on the landing page to "
                "recover it. The URL may need to be refreshed manually."
            ),
            AcquisitionState.AWAITING_SEARCH_PARAMS: (
                "The session expired but a search form was found. Provide search parameters "
                "(e.g., origin, destination, dates) to recover the data."
            ),
            AcquisitionState.EMPTY_RESPONSE: (
                "The page returned a successful response but contained no usable data. It may "
                "be a login wall, cookie consent page, or require JavaScript rendering."
            ),
            AcquisitionState.ANTI_BOT_BLOCKED: (
                "The page appears to be blocking automated access. Try again later or use a different approach."
            ),
            AcquisitionState.PATH_CHANGED: "The URL path changed. Data was extracted from the new page.",
            AcquisitionState.CROSS_DOMAIN: ("The URL redirected to a different domain. The original site may have changed."),
        }
        return messages.get(self.state, "URL acquisition completed.")

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dict compatible with the existing redirect_info format.

        This provides backward compatibility while the API transitions
        from the old dict-based redirect_info to the new AcquisitionLineage.
        """
        redirected = self.state not in (
            AcquisitionState.DIRECT,
            AcquisitionState.RECOVERED,
            AcquisitionState.EMPTY_RESPONSE,
            AcquisitionState.ANTI_BOT_BLOCKED,
            AcquisitionState.CROSS_DOMAIN,
        )

        # Map AcquisitionState to the legacy redirect_type values
        redirect_type_map = {
            AcquisitionState.DIRECT: "none",
            AcquisitionState.REDIRECTED: "path_changed",
            AcquisitionState.HOMEPAGE_REDIRECT: "homepage_redirect",
            AcquisitionState.SESSION_EXPIRED: "session_expired",
            AcquisitionState.RECOVERED: "none",
            AcquisitionState.RECOVERY_FAILED: "session_expired",
            AcquisitionState.NO_SEARCH_FORM: "session_expired",
            AcquisitionState.AWAITING_SEARCH_PARAMS: "session_expired",
            AcquisitionState.EMPTY_RESPONSE: "none",
            AcquisitionState.ANTI_BOT_BLOCKED: "none",
            AcquisitionState.PATH_CHANGED: "path_changed",
            AcquisitionState.CROSS_DOMAIN: "none",
            AcquisitionState.DOMAIN_COOLDOWN: "none",
        }

        return {
            "state": self.state.value,
            "redirected": redirected,
            "redirect_type": redirect_type_map.get(self.state, "none"),
            "message": self.message,
            "user_message": self.get_user_message(),
            "original_url": self.original_url,
            "final_url": self.final_url,
            "fetch_method": self.fetch_method,
            "recovery_method": self.recovery_method,
            "recovered_url": self.recovered_url,
            "session_bound": self.session_bound,
            "ephemeral_params": self.ephemeral_params,
            "data_evidence_score": self.data_evidence_score,
            "network_payloads_found": self.network_payloads_found,
            "forms_detected": self.forms_detected,
            "containers_detected": self.containers_detected,
            "anti_bot_score": self.anti_bot_score,
            "visible_text_length": self.visible_text_length,
            "recommended_next_action": self.recommended_next_action,
        }

    @classmethod
    def from_redirect_info(
        cls,
        redirect_info: dict[str, Any],
        original_url: str,
        final_url: str,
        fetch_method: str = "",
        search_recovery: dict | None = None,
        search_form: dict | None = None,
        search_params: dict | None = None,
    ) -> AcquisitionLineage:
        """Build an AcquisitionLineage from the legacy redirect_info dict.

        Infers the correct AcquisitionState by combining redirect_type
        with search recovery context.
        """
        redirect_type = redirect_info.get("redirect_type", "none")
        redirected = redirect_info.get("redirected", False)
        message = redirect_info.get("message", "")

        # Determine state from redirect_type + recovery context
        if not redirected:
            # No redirect — but check if recovery happened
            if "recovered" in message.lower() or fetch_method == "search_form_post":
                state = AcquisitionState.RECOVERED
                recovered_url = final_url if final_url != original_url else None
                return cls(
                    original_url=original_url,
                    final_url=final_url,
                    state=state,
                    message=(
                        message
                        if "recovered" in message.lower()
                        else "Search session was recovered via form submission → fresh results page"
                    ),
                    fetch_method=fetch_method,
                    recovery_method="search_form_post",
                    recovered_url=recovered_url,
                )
            state = AcquisitionState.DIRECT
        else:
            # There was a redirect — classify it
            state_map = {
                "session_expired": AcquisitionState.SESSION_EXPIRED,
                "homepage_redirect": AcquisitionState.HOMEPAGE_REDIRECT,
                "path_changed": AcquisitionState.PATH_CHANGED,
            }
            state = state_map.get(redirect_type, AcquisitionState.REDIRECTED)

            # Refine SESSION_EXPIRED based on recovery context
            if state == AcquisitionState.SESSION_EXPIRED:
                if search_recovery and search_recovery.get("success"):
                    state = AcquisitionState.RECOVERED
                    message = "Search session was recovered via form submission → fresh results page"
                elif search_recovery and not search_recovery.get("success"):
                    state = AcquisitionState.RECOVERY_FAILED
                elif search_form is not None and search_form.get("detected") and not search_params:
                    state = AcquisitionState.AWAITING_SEARCH_PARAMS
                elif search_form is not None and not search_form.get("detected"):
                    state = AcquisitionState.NO_SEARCH_FORM

        lineage = cls(
            original_url=original_url,
            final_url=final_url,
            state=state,
            message=message,
            fetch_method=fetch_method,
        )

        # Add recovery details if applicable
        if state == AcquisitionState.RECOVERED and search_recovery:
            lineage.recovery_method = "search_form_post"
            lineage.recovered_url = search_recovery.get("fresh_url")

        return lineage
