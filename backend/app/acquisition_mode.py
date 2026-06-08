"""Acquisition mode — controls how aggressively the system acquires data.

Provides escalation logic that progressively tries more aggressive approaches:
  STANDARD → AGGRESSIVE → DEEP_SCAN

Each mode determines:
  - Whether to attempt session recovery
  - Whether to use Playwright rendering
  - Whether to try alternative fetch strategies
  - How many retries to attempt
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.config import settings


class AcquisitionMode(StrEnum):
    """Acquisition mode controlling fetch aggressiveness and recovery behavior."""

    # Standard mode: direct fetch, basic redirect handling
    STANDARD = "standard"

    # Aggressive mode: session recovery, search form submission
    AGGRESSIVE = "aggressive"

    # Deep scan mode: all recovery strategies, multiple retries, fallback
    # rendering
    DEEP_SCAN = "deep_scan"


@dataclass
class AcquisitionConfig:
    """Configuration derived from an AcquisitionMode.

    Controls the behavior of analyze_url_for_fields and related functions.
    """

    mode: AcquisitionMode = AcquisitionMode.STANDARD

    # Whether to attempt session recovery when a session expires
    attempt_recovery: bool = False

    # Whether to use Playwright for JavaScript rendering
    use_playwright: bool = True

    # Whether to try search form submission for recovery
    attempt_search_form: bool = False

    # Maximum number of fetch retries
    max_retries: int = 1

    # Whether to try alternative fetch strategies on failure
    try_alternatives: bool = False

    # Whether to detect and handle empty-but-200 responses
    detect_empty_responses: bool = True

    # Whether to detect session-bound URL parameters
    detect_session_params: bool = True

    # Timeout multiplier (1.0 = normal, 2.0 = double timeout)
    timeout_multiplier: float = 1.0

    @classmethod
    def from_mode(cls, mode: AcquisitionMode) -> AcquisitionConfig:
        """Create an AcquisitionConfig from an AcquisitionMode."""
        if mode == AcquisitionMode.STANDARD:
            return cls(
                mode=mode,
                attempt_recovery=False,
                use_playwright=True,
                attempt_search_form=False,
                max_retries=settings.ACQUISITION_STANDARD_MAX_RETRIES,
                try_alternatives=False,
                detect_empty_responses=True,
                detect_session_params=True,
                timeout_multiplier=1.0,
            )
        if mode == AcquisitionMode.AGGRESSIVE:
            return cls(
                mode=mode,
                attempt_recovery=True,
                use_playwright=True,
                attempt_search_form=True,
                max_retries=settings.ACQUISITION_AGGRESSIVE_MAX_RETRIES,
                try_alternatives=True,
                detect_empty_responses=True,
                detect_session_params=True,
                timeout_multiplier=settings.ACQUISITION_AGGRESSIVE_TIMEOUT_MULT,
            )
        if mode == AcquisitionMode.DEEP_SCAN:
            return cls(
                mode=mode,
                attempt_recovery=True,
                use_playwright=True,
                attempt_search_form=True,
                max_retries=settings.ACQUISITION_DEEP_SCAN_MAX_RETRIES,
                try_alternatives=True,
                detect_empty_responses=True,
                detect_session_params=True,
                timeout_multiplier=settings.ACQUISITION_DEEP_SCAN_TIMEOUT_MULT,
            )
        return cls(mode=mode)


def escalate_mode(current_mode: AcquisitionMode) -> AcquisitionMode:
    """Escalate to the next more aggressive acquisition mode.

    STANDARD → AGGRESSIVE → DEEP_SCAN → DEEP_SCAN (stays at max)
    """
    escalation = {
        AcquisitionMode.STANDARD: AcquisitionMode.AGGRESSIVE,
        AcquisitionMode.AGGRESSIVE: AcquisitionMode.DEEP_SCAN,
        AcquisitionMode.DEEP_SCAN: AcquisitionMode.DEEP_SCAN,
    }
    return escalation[current_mode]


def should_escalate(
    current_mode: AcquisitionMode,
    acquisition_state: str,
    empty_response: bool = False,  # noqa: FBT001, FBT002
) -> bool:
    """Determine whether acquisition should escalate to a more aggressive mode.

    Escalation triggers:
    - Session expired → escalate from STANDARD to AGGRESSIVE
    - Recovery failed → escalate from AGGRESSIVE to DEEP_SCAN
    - Empty response state → escalate to try different rendering
    - Anti-bot blocked → escalate to try stealth

    A plain empty_response boolean only triggers escalation from STANDARD,
    since AGGRESSIVE / DEEP_SCAN already have empty-response detection enabled.
    """
    if current_mode == AcquisitionMode.DEEP_SCAN:
        return False  # Already at max

    escalation_triggers = {
        "session_expired",
        "recovery_failed",
        "empty_response",
        "anti_bot_blocked",
    }

    if acquisition_state in escalation_triggers:
        return True

    return bool(empty_response and current_mode == AcquisitionMode.STANDARD)
