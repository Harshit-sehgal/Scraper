"""LLM cascade circuit breaker.

Brake against repeated cascade exhaustions: when ``llm_json``,
``llm_json_fast``, or ``llm_text`` exhausts every provider in the
cascade ``LLM_CIRCUIT_FAILURE_THRESHOLD`` times in a row, the
breaker opens and short-circuits subsequent calls for
``LLM_CIRCUIT_OPEN_WINDOW_SECONDS``.  After the window elapses, the
breaker enters a half-open state: ``LLM_CIRCUIT_HALF_OPEN_MAX_PROBES``
calls are permitted; if they succeed, the circuit closes again,
otherwise it re-opens for another full window.

Rationale: a misconfigured or rate-limited provider causes every
cascade call to take the full timeout (~45s) before returning
empty — burning through token budget, blocking workers, and producing
silent-empty-structured-data in the meantime.  Calling code that
opts into ``raise_on_failure=True`` still sees the except stack on
the first failure, but subsequent failures are stopped at the
breaker with a :class:`LLMCircuitOpen` immediately, which is the
fail-fast outcome we want.

Disable with ``DATAFORGE_LLM_CIRCUIT_ENABLED=false`` when running
test fixtures that intentionally exercise the cascade-exhaustion
path.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Final

logger = logging.getLogger(__name__)

# States
CLOSED: Final[str] = "closed"
OPEN: Final[str] = "open"
HALF_OPEN: Final[str] = "half_open"


class LLMCircuitOpen(RuntimeError):
    """Raised when the LLM cascade circuit breaker is open.

    Carries the seconds remaining before the breaker will allow a
    probe call through, so callers can pick a sensible backoff
    without guessing.
    """

    def __init__(
        self,
        opens_until: float,
        failure_count: int,
        last_error: BaseException | None,
    ) -> None:
        self.opens_until = opens_until
        self.failure_count = failure_count
        self.last_error = last_error
        time_remaining = max(0.0, opens_until - time.monotonic())
        super().__init__(
            f"LLM cascade breaker is OPEN ({failure_count} consecutive failures, "
            f"reopens in {time_remaining:.1f}s; last error={last_error!r})"
        )


_DEFAULT_FAIL_THRESHOLD: Final[int] = 5
_DEFAULT_OPEN_WINDOW: Final[int] = 60
_DEFAULT_HALF_OPEN_PROBES: Final[int] = 1


class LLMCascadeBreaker:
    """Process-wide cascade circuit breaker.

    Multiple public LLM functions share the same breaker so a failure
    on any of them counts toward the same global threshold.  This
    matches the operational reality — if Groq is throttled, all
    three functions will fail in lockstep until the platform stops
    rate-limiting.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = _DEFAULT_FAIL_THRESHOLD,
        open_window_seconds: int = _DEFAULT_OPEN_WINDOW,
        half_open_max_probes: int = _DEFAULT_HALF_OPEN_PROBES,
    ) -> None:
        self._failure_threshold = max(1, int(failure_threshold))
        self._open_window_seconds = max(1, int(open_window_seconds))
        self._half_open_max_probes = max(1, int(half_open_max_probes))

        self._lock = threading.Lock()
        self._state: str = CLOSED
        self._consecutive_failures: int = 0
        self._opens_at: float = 0.0
        self._last_error: BaseException | None = None
        self._half_open_probes_used: int = 0

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_recover_to_half_open()
            return self._state

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    def _maybe_recover_to_half_open(self) -> None:
        """Promote OPEN → HALF_OPEN once the open window has passed."""
        if self._state == OPEN and time.monotonic() >= self._opens_at:
            self._state = HALF_OPEN
            self._half_open_probes_used = 0
            logger.info(
                "LLM cascade breaker auto-recovers to HALF_OPEN (probes=%d)",
                self._half_open_max_probes,
            )

    def check(self, *, enabled: bool) -> None:
        """Raise :class:`LLMCircuitOpen` if the breaker is OPEN.

        When ``enabled=False`` (e.g. test fixtures), no-op.
        """
        if not enabled:
            return
        with self._lock:
            self._maybe_recover_to_half_open()
            if self._state == OPEN:
                opens_until = self._opens_at
                raise LLMCircuitOpen(
                    opens_until=opens_until,
                    failure_count=self._consecutive_failures,
                    last_error=self._last_error,
                )
            if self._state == HALF_OPEN:
                if self._half_open_probes_used >= self._half_open_max_probes:
                    # All permitted probes have already been used in this
                    # half-open window without success — keep the
                    # breaker open until the next window.
                    self._state = OPEN
                    self._opens_at = time.monotonic() + self._open_window_seconds
                    raise LLMCircuitOpen(
                        opens_until=self._opens_at,
                        failure_count=self._consecutive_failures,
                        last_error=self._last_error,
                    )
                self._half_open_probes_used += 1

    def record_success(self, *, enabled: bool) -> None:
        """Reset the breaker after a successful call closes the cascade."""
        if not enabled:
            return
        with self._lock:
            if self._state != CLOSED:
                logger.info(
                    "LLM cascade breaker closes after success (was %s)",
                    self._state,
                )
            self._state = CLOSED
            self._consecutive_failures = 0
            self._last_error = None
            self._half_open_probes_used = 0

    def record_failure(self, error: BaseException, *, enabled: bool) -> None:
        """Increment the failure counter and open the breaker if needed."""
        if not enabled:
            return
        with self._lock:
            self._consecutive_failures += 1
            self._last_error = error
            if self._state == CLOSED and self._consecutive_failures >= self._failure_threshold:
                self._state = OPEN
                self._opens_at = time.monotonic() + self._open_window_seconds
                logger.warning(
                    "LLM cascade breaker OPENS after %d consecutive failures (reopens at %.1fs, last_error=%r)",
                    self._consecutive_failures,
                    self._opens_at,
                    error,
                )
            elif self._state == HALF_OPEN:
                # A failure during a half-open probe re-opens the
                # breaker immediately, skipping the "wait for window"
                # step.
                self._state = OPEN
                self._opens_at = time.monotonic() + self._open_window_seconds
                logger.warning(
                    "LLM cascade breaker re-opens after half-open probe failed (reopens at %.1fs, last_error=%r)",
                    self._opens_at,
                    error,
                )

    def snapshot(self) -> dict[str, object]:
        """Return a serialisable view of breaker state for /metrics."""
        with self._lock:
            self._maybe_recover_to_half_open()
            opens_in = None
            if self._state == OPEN:
                opens_in = max(0.0, self._opens_at - time.monotonic())
            return {
                "state": self._state,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self._failure_threshold,
                "open_window_seconds": self._open_window_seconds,
                "half_open_max_probes": self._half_open_max_probes,
                "half_open_probes_used": self._half_open_probes_used,
                "opens_in_seconds": opens_in,
                "last_error": repr(self._last_error) if self._last_error else None,
            }


_breaker_lock = threading.Lock()
_breaker: LLMCascadeBreaker | None = None


def _settings_or_defaults():
    """Lazy import of the settings module to avoid circular imports."""
    try:
        from app.config import settings as _settings

        return (
            _settings.LLM_CIRCUIT_ENABLED,
            _settings.LLM_CIRCUIT_FAILURE_THRESHOLD,
            _settings.LLM_CIRCUIT_OPEN_WINDOW_SECONDS,
            _settings.LLM_CIRCUIT_HALF_OPEN_MAX_PROBES,
        )
    except (ImportError, AttributeError, ValueError) as exc:
        logger.debug(
            "LLM cascade breaker settings unavailable; falling back to defaults: %s",
            exc,
        )
        return (True, _DEFAULT_FAIL_THRESHOLD, _DEFAULT_OPEN_WINDOW, _DEFAULT_HALF_OPEN_PROBES)


def get_llm_cascade_breaker() -> LLMCascadeBreaker:
    """Return the process-wide LLM cascade breaker.

    Configuration is captured at first use; call :func:`reset_cascade_breaker`
    after a settings change to disturb an already-initialised breaker.
    """
    global _breaker
    with _breaker_lock:
        if _breaker is None:
            _enabled, threshold, window, half_open_probes = _settings_or_defaults()
            _breaker = LLMCascadeBreaker(
                failure_threshold=threshold,
                open_window_seconds=window,
                half_open_max_probes=half_open_probes,
            )
        return _breaker


def reset_cascade_breaker() -> None:
    """Drop the cached breaker.  Test helper.

    The next call to :func:`get_llm_cascade_breaker` will re-load
    configuration from :mod:`app.config`.
    """
    global _breaker
    with _breaker_lock:
        _breaker = None
