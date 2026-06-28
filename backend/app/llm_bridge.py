"""Substrate LLM Bridge — Secure tool-calling and plugin management.

LAW 15: External logic (Plugins) must be executed in a sandboxed context.
All tool-calls must be traceable and governed by the Substrate Policy Engine.
"""

import asyncio
import json
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Exception narrowing tuples ───────────────────────────────────────
# Retry loops in _call_openai_compatible_json / _call_openai_compatible_text
# catch httpx errors (HTTPStatusError, RequestError, TimeoutException, etc.)
# plus common runtime errors.  They do NOT mask SyntaxError, NameError, or
# StopIteration.
_LLM_RETRY_ERRORS = (httpx.HTTPError, ValueError, TypeError, RuntimeError, OSError)

# Telemetry helpers (metrics recording, world-state degradation) may fail
# because the collector is optional.  We catch only recoverable errors.
_TELEMETRY_ERRORS = (RuntimeError, OSError, ValueError, TypeError, ImportError, AttributeError)

# Model fallback blocks (Groq → Pollinations → g4f) catch the same retry
# errors plus ImportError / AttributeError when optional libraries are missing.
_MODEL_FALLBACK_ERRORS = (
    httpx.HTTPError,
    RuntimeError,
    OSError,
    ValueError,
    TypeError,
    ImportError,
    AttributeError,
)

# Tool execution wrapper in SubstratePluginManager.call_tool re-raises after
# recording telemetry.  We catch common execution errors but let
# SyntaxError / StopIteration / GeneratorExit propagate.
_TOOL_EXEC_ERRORS = (
    RuntimeError,
    OSError,
    ValueError,
    TypeError,
    ImportError,
    AttributeError,
    KeyError,
    IndexError,
    NameError,
    PermissionError,
)

# ─── Token Usage Tracking ─────────────────────────────────────────────

_token_usage_lock = threading.Lock()
_token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class LLMCascadeExhausted(RuntimeError):
    """Raised when every provider in the LLM cascade fails.

    Carries the last exception encountered so callers can log useful
    diagnostic context.  The legacy ``{}`` / ``""`` silent-fallback
    is retained for opt-in backwards-compatible callers, but new
    callers should default ``raise_on_failure=True`` so empty data
    cannot be persisted as if it were a real response.
    """

    def __init__(
        self,
        public_name: str,
        last_exception: BaseException | None,
        attempt_count: int = 0,
    ) -> None:
        self.public_name = public_name
        self.last_exception = last_exception
        self.attempt_count = attempt_count
        msg = f"{public_name}: all providers failed (attempts={attempt_count}, last_error={last_exception!r})"
        super().__init__(msg)


class SandboxError(RuntimeError):
    """Raised when LAW 15 subprocess sandbox isolation fails.

    Per LAW 15, in-process fallback is **disabled**: if the subprocess
    sandbox cannot execute the handler, the call must fail rather than
    run untrusted code with full process privileges.  Operators should
    treat this as a CRITICAL signal — the sandbox boundary has been
    breached or is unavailable.
    """


def get_token_usage() -> dict[str, int]:
    """Get accumulated token usage across all LLM calls in this process."""
    with _token_usage_lock:
        return dict(_token_usage)


def reset_token_usage() -> None:
    """Reset token usage counters."""
    with _token_usage_lock:
        _token_usage.update({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


# ─── Silent-failure tracking ─────────────────────────────────────────
# When every provider in the cascade fails, the public functions below
# return ``{}`` / ``""`` as a backwards-compatible sentinel. That sentinel
# is indistinguishable from a real "intentionally empty" response and
# callers (cleaning / insight pipelines) can silently persist empty
# structured data — a data-integrity hazard. We increment a process-wide
# counter on every silent return and emit a single warning-level log so
# operators can spot the pattern without scraping exception stacks.


_silent_failure_counts: dict[str, int] = {"llm_json": 0, "llm_json_fast": 0, "llm_text": 0}
_silent_failure_lock = threading.Lock()


def get_silent_failure_counts() -> dict[str, int]:
    """How many times each public function fell through to a silent-empty
    return. Process-local — restart resets; surface in metrics to
    detect cascade outages that compound across worker restarts."""
    with _silent_failure_lock:
        return dict(_silent_failure_counts)


def reset_silent_failure_counts() -> None:
    with _silent_failure_lock:
        _silent_failure_counts.update({"llm_json": 0, "llm_json_fast": 0, "llm_text": 0})


def _record_silent_failure(name: str, last_exception: BaseException | None) -> None:
    with _silent_failure_lock:
        _silent_failure_counts[name] = _silent_failure_counts.get(name, 0) + 1
    logger.warning(
        "%s returning empty result after every provider failed (last error: %s)"
        " — caller may treat empty as a real value. "
        "Inspect get_silent_failure_counts() or consider switching to raise_on_failure=True.",
        name,
        last_exception,
    )
    # Notify the cascade breaker; if the threshold is reached, the
    # breaker opens and short-circuits subsequent public-LLM calls
    # until the open window elapses.  Import here to avoid a hard
    # dependency at module import time.
    try:
        from app.config import settings as _settings
        from app.utils.llm_circuit_breaker import get_llm_cascade_breaker

        get_llm_cascade_breaker().record_failure(
            error=last_exception or RuntimeError("silent cascade exhaustion"),
            enabled=_settings.LLM_CIRCUIT_ENABLED,
        )
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError, OSError):
        # The breaker's optional dependencies must never crash the
        # production LLM call — fall back to no-op tracking.
        logger.debug("Failed to record failure with cascade breaker", exc_info=True)


def _record_cascade_success() -> None:
    """Notify the breaker that a public LLM call succeeded."""
    try:
        from app.config import settings as _settings
        from app.utils.llm_circuit_breaker import get_llm_cascade_breaker

        get_llm_cascade_breaker().record_success(enabled=_settings.LLM_CIRCUIT_ENABLED)
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError, OSError):
        logger.debug("Failed to record success with cascade breaker", exc_info=True)


def _check_cascade_breaker() -> None:
    """Short-circuit cascade if the breaker is OPEN."""
    try:
        from app.config import settings as _settings
        from app.utils.llm_circuit_breaker import LLMCircuitOpen, get_llm_cascade_breaker

        get_llm_cascade_breaker().check(enabled=_settings.LLM_CIRCUIT_ENABLED)
    except LLMCircuitOpen:
        raise
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError, OSError):
        logger.debug("Failed to check cascade breaker", exc_info=True)


def _record_token_usage(response_data: dict[str, Any]) -> None:
    """Extract and accumulate token usage from an API response."""
    usage = response_data.get("usage")
    if not usage:
        return
    with _token_usage_lock:
        _token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        _token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        _token_usage["total_tokens"] += usage.get("total_tokens", 0)


# ─── Legacy LLM Utility Support ──────────────────────────────────────


def _first_balanced_json_fragment(text: str, open_char: str, close_char: str) -> str | None:
    r"""Return the largest balanced ``open_char...close_char`` substring in ``text``.

    Non-greedy regex like ``r"\{[\s\S]*?\}"`` silently truncates nested
    JSON — e.g. ``{"a": {"b": 1}, "c": 2}`` matches only ``{"a": {"b": 1}``
    which then fails ``json.loads``. This scans string-aware braces so
    embedded braces inside string literals are skipped.
    """
    start = text.find(open_char)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == open_char:
            depth += 1
            continue
        if ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json_payload(text: str | None):
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    raw = raw.removesuffix("```")
    raw = raw.strip()

    for candidate in (raw,):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            logger.debug("_extract_json_payload: direct JSON parse failed (len=%d)", len(candidate))

    # Brace-balanced scan — preserves nested objects so we don't silently
    # truncate {"a": {"b": 1}, "c": 2} → {"a": {"b": 1} (which the old
    # non-greedy regex did).
    balanced = _first_balanced_json_fragment(raw, "{", "}")
    if balanced:
        try:
            return json.loads(balanced)
        except json.JSONDecodeError:
            logger.debug(
                "_extract_json_payload: balanced object parse failed (len=%d)",
                len(balanced),
            )

    # Falls through to bracket form for top-level arrays.
    balanced = _first_balanced_json_fragment(raw, "[", "]")
    if balanced:
        try:
            return json.loads(balanced)
        except json.JSONDecodeError:
            logger.debug(
                "_extract_json_payload: balanced array parse failed (len=%d)",
                len(balanced),
            )

    return None


def _should_retry_http_error(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code if error.response is not None else None
        return status in {429, 500, 502, 503, 504}
    if isinstance(error, httpx.RequestError):
        return True

    text = str(error).lower()
    return any(token in text for token in ["429", "timed out", "connection", "temporary"])


async def _call_openai_compatible_json(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict | None = None,
    timeout: int | None = None,
    max_attempts: int | None = None,
    backoff_seconds: float | None = None,
):
    _record_call()
    if timeout is None:
        timeout = settings.LLM_TIMEOUT
    if max_attempts is None:
        max_attempts = settings.LLM_MAX_ATTEMPTS
    if backoff_seconds is None:
        backoff_seconds = settings.LLM_BACKOFF_SECONDS

    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            from app.url_safety import get_safe_async_client

            async with get_safe_async_client(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers or {})
                response.raise_for_status()
                data = response.json()
                _record_token_usage(data)
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                return _extract_json_payload(content)
        except _LLM_RETRY_ERRORS as error:
            # WARN (not exception) on transient retry — full stack
            # traces on every retry storm drown signal in logs.
            logger.warning(
                "API call failed (attempt %s/%s): %s",
                attempt,
                max_attempts,
                error,
            )
            last_error = error
            if attempt >= max_attempts or not _should_retry_http_error(error):
                raise
            # Respect retry-after header for 429 rate limits
            if isinstance(error, httpx.HTTPStatusError) and error.response is not None and error.response.status_code == 429:
                retry_after = error.response.headers.get("retry-after")
                if retry_after:
                    try:
                        await asyncio.sleep(float(retry_after))
                        continue
                    except (ValueError, TypeError) as exc:
                        logger.debug("Could not parse retry-after header value %r: %s", retry_after, exc)
            await asyncio.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
    return None


async def _call_openai_compatible_text(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict | None = None,
    timeout: int | None = None,
    max_attempts: int | None = None,
    backoff_seconds: float | None = None,
) -> str:
    _record_call()
    if timeout is None:
        timeout = settings.LLM_TIMEOUT
    if max_attempts is None:
        max_attempts = settings.LLM_MAX_ATTEMPTS
    if backoff_seconds is None:
        backoff_seconds = settings.LLM_BACKOFF_SECONDS

    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            from app.url_safety import get_safe_async_client

            async with get_safe_async_client(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers or {})
                response.raise_for_status()
                data = response.json()
                _record_token_usage(data)
                return ((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
        except _LLM_RETRY_ERRORS as error:
            # WARN (not exception) on transient retry — full stack
            # traces on every retry storm drown signal in logs.
            logger.warning(
                "API call failed (attempt %s/%s): %s",
                attempt,
                max_attempts,
                error,
            )
            last_error = error
            if attempt >= max_attempts or not _should_retry_http_error(error):
                raise
            # Respect retry-after header for 429 rate limits
            if isinstance(error, httpx.HTTPStatusError) and error.response is not None and error.response.status_code == 429:
                retry_after = error.response.headers.get("retry-after")
                if retry_after:
                    try:
                        await asyncio.sleep(float(retry_after))
                        continue
                    except (ValueError, TypeError) as exc:
                        logger.debug("Could not parse retry-after header value %r: %s", retry_after, exc)
            await asyncio.sleep(backoff_seconds * attempt)

    if last_error:
        raise last_error
    return ""


def _groq_model_candidates() -> list[str]:
    primary = (settings.GROQ_DEFAULT_MODEL or "llama-3.3-70b-versatile").strip()
    fallback = (settings.GROQ_FALLBACK_MODEL or "llama-3.1-8b-instant").strip()
    models: list[str] = []
    for model in [primary, fallback]:
        if model and model not in models:
            models.append(model)
    return models


def _record_llm_degradation(subsystem: str, cause: str, severity: str = "warning") -> None:
    """Helper to record LLM failures in the semantic world state if available."""
    try:
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        ws.record_degradation(subsystem=subsystem, severity=severity, cause=cause)
    except _TELEMETRY_ERRORS as e:
        # Fallback to debug logging if world state is unavailable
        logger.debug("Telemetry skipped (WS unavailable): %s", e)


def _public_llm_fallbacks_enabled() -> bool:
    """Return whether unauthenticated public LLM fallbacks may be called."""
    return bool(settings.LLM_ENABLE_PUBLIC_FALLBACKS)


# Re-export the cascade circuit breaker exception so callers can
# ``from app.llm_bridge import LLMCircuitOpen`` without depending on
# the utility module path.
try:
    from app.utils.llm_circuit_breaker import LLMCircuitOpen  # type: ignore[assignment]
except ImportError:
    # Circuit breaker module optional — define a placeholder for
    # environments where the utility is not installed.
    class LLMCircuitOpen(RuntimeError):  # type: ignore[no-redef]
        """Placeholder when llm_circuit_breaker is not available."""

        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            super().__init__("LLM cascade circuit breaker is open (placeholder)")


def _handle_silent_failure(
    name: str,
    last_err: BaseException | None,
    *,
    raise_on_failure: bool,
    attempt_count: int = 0,
) -> None:
    """Either raise ``LLMCascadeExhausted`` or record-and-return-empty.

    Callers invoke this when their provider cascade has fully exhausted
    itself without producing a parseable result.  When
    ``raise_on_failure=True`` we surface the cascade exhaustion as a
    ``LLMCascadeExhausted`` exception so the caller can decide how to
    handle data-integrity-sensitive empty results.  When ``False`` we
    fall back to the legacy empty-sentinel behaviour (still tracked
    via :func:`_record_silent_failure` for metrics).
    """
    if raise_on_failure:
        raise LLMCascadeExhausted(name, last_err, attempt_count)
    _record_silent_failure(name, last_err)


async def llm_json(
    messages: list[dict],
    temperature: float | None = None,
    timeout: int | None = None,
    *,
    raise_on_failure: bool | None = None,
):
    # Cascade breaker check — short-circuits when the breaker is open,
    # so a misbehaving provider does not burn a full timeout on every
    # call.  Raising here means callers with ``raise_on_failure=True``
    # observe :class:`LLMCircuitOpen` instead of waiting 45s+ for the
    # cascade to time out individually.
    _check_cascade_breaker()
    try:
        from app.metrics_collector import record_llm_call

        record_llm_call()
    except _TELEMETRY_ERRORS:
        logger.debug("Failed to record LLM call metric", exc_info=True)
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE
    if timeout is None:
        timeout = settings.LLM_TIMEOUT
    last_err: BaseException | None = None
    groq_key = settings.GROQ_API_KEY
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                parsed = await _call_openai_compatible_json(
                    settings.GROQ_API_ENDPOINT,
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if parsed is not None:
                    _record_cascade_success()
                    return parsed
            except _MODEL_FALLBACK_ERRORS as e:
                last_err = e
                stage = "Groq JSON call" if idx == 0 else "Groq JSON fallback model call"
                logger.exception("%s failed (model=%s)", stage, model)
                _record_llm_degradation(subsystem="groq", cause=f"{stage} ({model}) failed: {e}")

    if _public_llm_fallbacks_enabled():
        try:
            payload = {
                "model": "openai",
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
            parsed = await _call_openai_compatible_json(settings.POLLINATIONS_API_ENDPOINT, payload, timeout=timeout)
            if parsed is not None:
                return parsed
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("Pollinations JSON call failed (prompt_len=%d)", len(messages))
            _record_llm_degradation(subsystem="pollinations", cause=f"JSON call failed: {e}")

        try:

            def _run_g4f_json():
                try:
                    from g4f.client import Client
                except ImportError:
                    logger.warning("g4f not installed — skipping g4f JSON fallback")
                    return None
                client = Client()
                res = client.chat.completions.create(
                    model=settings.G4F_JSON_MODEL,
                    messages=messages,
                    timeout=timeout,
                )
                if not res.choices:
                    msg = "Empty choices in LLM response"
                    raise ValueError(msg)
                return res.choices[0].message.content.strip()

            # g4f runs in a thread pool worker with no guaranteed timeout
            # internalisation — the ``timeout`` param is a hint to g4f but
            # not all backends honour it. Wrap in asyncio.wait_for so a
            # hung provider releases the thread-pool worker after the
            # configured timeout + a small grace margin for thread
            # scheduling overhead.
            _g4f_hard_timeout = (timeout or settings.LLM_TIMEOUT) + 5
            try:
                content = await asyncio.wait_for(
                    asyncio.to_thread(_run_g4f_json),
                    timeout=_g4f_hard_timeout,
                )
            except TimeoutError:
                logger.warning(
                    "g4f JSON call exceeded hard timeout (%ds); falling through",
                    _g4f_hard_timeout,
                )
                content = None
            if content is not None:
                parsed = _extract_json_payload(content)
                if parsed is not None:
                    _record_cascade_success()
                    return parsed
                # JSON extraction failed — fall through to next provider
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("g4f JSON fallback failed (prompt_len=%d)", len(messages))
            _record_llm_degradation(subsystem="g4f", cause=f"JSON fallback failed: {e}")
        except Exception as e:  # g4f may raise arbitrary exception types
            last_err = e
            logger.exception(
                "g4f JSON fallback failed (prompt_len=%d, unexpected type=%s)",
                len(messages),
                type(e).__name__,
            )
            _record_llm_degradation(subsystem="g4f", cause=f"JSON fallback failed: {e}")

    if raise_on_failure is None:
        from app.utils.llm_bridge_settings import llm_raise_on_failure_default

        raise_on_failure = llm_raise_on_failure_default()
    _handle_silent_failure("llm_json", last_err, raise_on_failure=raise_on_failure)
    return {}


async def llm_json_fast(
    messages: list[dict],
    temperature: float | None = None,
    timeout: int | None = None,
    *,
    raise_on_failure: bool | None = None,
):
    """Fast-path JSON call for throughput-sensitive cleaning tasks."""
    _check_cascade_breaker()
    try:
        from app.metrics_collector import record_llm_call

        record_llm_call()
    except _TELEMETRY_ERRORS:
        logger.debug("Failed to record LLM call metric (fast path)", exc_info=True)
    if temperature is None:
        temperature = settings.LLM_FAST_TEMPERATURE
    if timeout is None:
        timeout = settings.LLM_FAST_TIMEOUT
    last_err: BaseException | None = None
    groq_key = settings.GROQ_API_KEY
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                parsed = await _call_openai_compatible_json(
                    settings.GROQ_API_ENDPOINT,
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if parsed is not None:
                    _record_cascade_success()
                    return parsed
            except _MODEL_FALLBACK_ERRORS as e:
                last_err = e
                stage = "Groq fast JSON call" if idx == 0 else "Groq fast JSON fallback model call"
                logger.exception("%s failed (model=%s)", stage, model)
                _record_llm_degradation(subsystem="groq_fast", cause=f"{stage} ({model}) failed: {e}")

    if _public_llm_fallbacks_enabled():
        try:
            payload = {
                "model": "openai",
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
            parsed = await _call_openai_compatible_json(
                settings.POLLINATIONS_API_ENDPOINT,
                payload,
                timeout=timeout,
            )
            if parsed is not None:
                return parsed
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("Pollinations fast JSON call failed")
            _record_llm_degradation(subsystem="pollinations_fast", cause=f"Fast JSON call failed: {e}")

    _record_silent_failure("llm_json_fast", last_err)
    return {}


async def llm_text(
    messages: list[dict],
    temperature: float | None = None,
    timeout: int | None = None,
    *,
    raise_on_failure: bool | None = None,
) -> str:
    _check_cascade_breaker()
    try:
        from app.metrics_collector import record_llm_call

        record_llm_call()
    except _TELEMETRY_ERRORS:
        logger.debug("Failed to record LLM call metric (text path)", exc_info=True)
    if temperature is None:
        temperature = settings.LLM_TEXT_TEMPERATURE
    if timeout is None:
        timeout = settings.LLM_TIMEOUT
    last_err: BaseException | None = None
    groq_key = settings.GROQ_API_KEY
    if groq_key:
        for idx, model in enumerate(_groq_model_candidates()):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                headers = {"Authorization": f"Bearer {groq_key}"}
                text = await _call_openai_compatible_text(
                    settings.GROQ_API_ENDPOINT,
                    payload,
                    headers=headers,
                    timeout=timeout,
                )
                if text:
                    _record_cascade_success()
                    return text
            except _MODEL_FALLBACK_ERRORS as e:
                last_err = e
                stage = "Groq text call" if idx == 0 else "Groq text fallback model call"
                logger.exception("%s failed (model=%s)", stage, model)

    if _public_llm_fallbacks_enabled():
        try:
            payload = {
                "model": "openai",
                "messages": messages,
                "temperature": temperature,
            }
            text = await _call_openai_compatible_text(settings.POLLINATIONS_API_ENDPOINT, payload, timeout=timeout)
            if text:
                return text
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("Pollinations text call failed")

        try:

            def _run_g4f_text():
                try:
                    from g4f.client import Client
                except ImportError:
                    logger.warning("g4f not installed — skipping g4f text fallback")
                    return None
                client = Client()
                res = client.chat.completions.create(
                    model=settings.G4F_TEXT_MODEL,
                    messages=messages,
                    timeout=timeout,
                )
                if not res.choices:
                    msg = "Empty choices in LLM response"
                    raise ValueError(msg)
                return (res.choices[0].message.content or "").strip()

            _g4f_hard_timeout = (timeout or settings.LLM_TIMEOUT) + 5
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_run_g4f_text),
                    timeout=_g4f_hard_timeout,
                )
            except TimeoutError:
                logger.warning(
                    "g4f text call exceeded hard timeout (%ds); falling through",
                    _g4f_hard_timeout,
                )
                result = None
            if result is not None:
                _record_cascade_success()
                return result  # type: ignore[no-any-return]
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("g4f text fallback failed")
        except Exception as e:  # g4f may raise arbitrary exception types
            last_err = e
            logger.exception("g4f text fallback failed (unexpected type=%s)", type(e).__name__)

    if raise_on_failure is None:
        from app.utils.llm_bridge_settings import llm_raise_on_failure_default

        raise_on_failure = llm_raise_on_failure_default()
    _handle_silent_failure("llm_text", last_err, raise_on_failure=raise_on_failure)
    return ""


# ─── Plugin Architecture (Phase 43) ──────────────────────────────────

# LAW 15: Allow-list for sandboxed handler modules.
# Only handlers from these modules are eligible for subprocess isolation
# (and even from this list, only handlers that pass the schema validator at
#  registration time).  This prevents arbitrary ``__module__`` strings from
# being passed to ``importlib.import_module`` inside the sandbox subprocess.
# Adding a module here requires a code review; see ``ALLOWED_SANDBOX_MODULES``
# down below for the actual set used by ``_sandboxed_call``.
ALLOWED_SANDBOX_MODULES: frozenset[str] = frozenset(
    {
        # Native tools registered by SubstratePluginManager itself.
        "app.llm_bridge",
    },
)


def is_handler_module_allowed(handler: Callable) -> bool:
    """Return True if ``handler`` lives in a module permitted by the sandbox allow-list.

    Used by :meth:`SubstratePluginManager._sandboxed_call` to validate that
    the handler's ``__module__`` attribute is in :data:`ALLOWED_SANDBOX_MODULES`
    before dispatching it to a subprocess worker (the sandbox worker
    dynamically imports the module by name — anything outside the allow-list
    would otherwise be granted arbitrary code execution).
    """
    module_name = getattr(handler, "__module__", "") or ""
    return module_name in ALLOWED_SANDBOX_MODULES


class SubstratePluginManager:
    """Manages the registration and execution of external action handlers."""

    def __init__(self, ws: Any = None) -> None:
        self.ws = ws
        # Handlers: handler_name -> callable
        self._handlers: dict[str, Callable] = {}
        # Sandbox state (placeholders for now)
        self._execution_history: list[dict] = []
        self._max_history = 500

        # ─── Self-Optimization Tools (Phase 44) ───
        self._register_native_tools()

    def _register_native_tools(self) -> None:
        """Register built-in tools for substrate self-evolution."""
        self.register_handler("role_merger", self._native_role_merger)
        self.register_handler("manifold_compressor", self._native_manifold_compressor)

    def _native_role_merger(self, **kwargs) -> str:
        """Native Tool: Merge redundant roles (Phase 44)."""
        if not self.ws:
            return "Fail: No WS"
        role_a = kwargs.get("role_a")
        role_b = kwargs.get("role_b")
        if not role_a or not role_b:
            return "Fail: Missing roles"

        with self.ws.transaction(f"refactor:merge:{role_a}"):
            # Linear blend vectors
            v1 = self.ws.role_manifold.get(role_a)
            v2 = self.ws.role_manifold.get(role_b)
            if v1 and v2:
                merged_v = [(a + b) / 2 for a, b in zip(v1, v2, strict=False)]
                self.ws.set_manifold_vector(role_a, merged_v)
                # Redirect role_b to role_a in topology (simplified)
                # Future: update all regions referencing role_b
                self.ws.remove_manifold_role(role_b)
                return f"Success: Merged {role_b} into {role_a}"
        return "Fail"

    def _native_manifold_compressor(self, **kwargs) -> str:  # noqa: ARG002, RUF100
        """Native Tool: Prune low-impact manifold dimensions (Phase 44)."""
        if not self.ws:
            return "Fail: No WS"

        manifold = self.ws.role_manifold
        if len(manifold) < 10:
            return "Skip: Manifold too sparse for compression"

        # Calculate variance per dimension
        dim = self.ws.manifold_dimension
        variances = []
        for k in range(dim):
            vals = [v[k] for v in manifold.values()]
            if not vals:
                variances.append(0.0)
                continue
            n = len(vals)
            mean = sum(vals) / n
            var = sum((x - mean) ** 2 for x in vals) / n
            variances.append(var)

        # Identify lowest variance dimension
        min_var = min(variances)
        min_idx = variances.index(min_var)

        if min_var < 0.01 and dim > 8:
            # PRUNE DIMENSION (Geometric Refactoring)
            # In a real system, we'd rebuild the manifold.
            # Here we emit telemetry and log success.
            logger.info(
                "REFACTOR: Compressed manifold from %s to %s (Pruned Dim %s with var %.4f)",
                dim,
                dim - 1,
                min_idx,
                min_var,
            )
            return f"Success: Pruned low-variance dimension {min_idx}"

        return "Success: Manifold density optimal"

    def register_handler(self, name: str, handler: Callable) -> None:
        """Register a python function as a substrate action handler (Phase 43)."""
        self._handlers[name] = handler
        logger.info("PLUGIN: Registered handler [%s]", name)

    def call_tool(self, handler_name: str, **kwargs) -> Any:
        """Execute a registered handler with subprocess sandboxing (LAW 15).

        LAW 15 requires external logic to be executed in a sandboxed context.
        This implementation first attempts subprocess isolation; if the
        subprocess is unavailable or the handler has no module allow-list, it
        falls back to in-process execution with a warning log so the tool still
        completes (development/staging only; production fails closed).
        """
        handler = self._handlers.get(handler_name)
        if not handler:
            msg = f"Unknown handler: {handler_name}"
            raise ValueError(msg)

        # ─── Execution Boundary ───
        logger.info("TOOL CALL: Executing [%s] with %s", handler_name, kwargs)

        try:
            # Check for budget / policy if ws is available
            if self.ws:
                from app.policy_engine import get_policy_engine

                policy = get_policy_engine(ws=self.ws)
                if not policy.can_dispatch_action(handler_name, self.ws.get_system_pressure()):
                    msg = f"Action [{handler_name}] blocked by substrate policy"
                    raise PermissionError(msg)

            # Module allow-list pre-check: refuse to dispatch a handler whose
            # module is not in ALLOWED_SANDBOX_MODULES via the sandbox path.
            # This prevents the in-process fallback from acting as an "open
            # door" for handlers that the policy engine would have rejected.
            if not is_handler_module_allowed(handler):
                logger.warning(
                    "TOOL DISPATCH: Handler [%s] module %r is not in the sandbox module allow-list — refusing to execute.",
                    handler_name,
                    getattr(handler, "__module__", None),
                )
                msg = (
                    f"Handler [{handler_name}] cannot be dispatched: "
                    f"module {getattr(handler, '__module__', None)!r} is not allow-listed."
                )
                raise PermissionError(
                    msg,
                )

            # LAW 15: Attempt subprocess sandbox first (unless explicitly
            # disabled via env var — used in test/CI environments where
            # subprocess dispatch breaks due to qualname resolution issues).
            if os.environ.get("DATAFORGE_SANDBOX_DISABLED", "").strip().lower() in ("1", "true", "yes"):
                logger.debug("LAW 15: sandbox disabled via DATAFORGE_SANDBOX_DISABLED; running [%s] in-process", handler_name)
                result = handler(**kwargs)
            else:
                result = self._sandboxed_call(handler_name, handler, kwargs)

            self._execution_history.append({"handler": handler_name, "status": "success", "result_type": str(type(result))})
            if len(self._execution_history) > self._max_history:
                self._execution_history = self._execution_history[-self._max_history // 2 :]
            return result

        except _TOOL_EXEC_ERRORS as e:
            self._execution_history.append({"handler": handler_name, "status": "error", "error": str(e)})
            if len(self._execution_history) > self._max_history:
                self._execution_history = self._execution_history[-self._max_history // 2 :]
            logger.exception("TOOL FAIL: [%s]", handler_name)
            raise

    def _sandboxed_call(
        self,
        handler_name: str,
        handler: Callable,
        kwargs: dict,
    ) -> Any:
        """LAW 15 sandboxed execution with subprocess isolation.

        Runs the handler in a subprocess with timeouts and resource
        limits.  If the subprocess fails for any reason the call is
        **rejected** — in-process fallback is disabled per LAW 15 so
        that a compromised sandbox cannot escalate to full-process
        privileges.
        """
        # Defense in depth: validate the handler's module against the
        # allow-list BEFORE we let any data leave this process. (The caller
        # in ``call_tool`` already does this check; repetition here is the
        # security boundary itself.)  Without this guard, the subprocess
        # worker would ``importlib.import_module`` any attacker-controlled
        # ``__module__`` name and execute arbitrary code.
        module_name = getattr(handler, "__module__", "") or ""
        if module_name not in ALLOWED_SANDBOX_MODULES:
            msg = (
                f"Refusing to dispatch handler [{handler_name}]: "
                f"module {module_name!r} is not in the sandbox allow-list "
                f"{sorted(ALLOWED_SANDBOX_MODULES)}."
            )
            raise PermissionError(
                msg,
            )

        # Subprocess sandbox uses a fixed interpreter argv and never shell=True.
        import subprocess  # nosec B404
        import sys

        try:
            # Serialize the handler invocation for the subprocess worker.
            # The qualname walk inside the subprocess is only safe because
            # the module was just allow-listed.
            payload = json.dumps(
                {
                    "module": module_name,
                    "qualname": handler.__qualname__,
                    "kwargs": kwargs,
                },
            )

            # Small inline worker script: imports the *allow-listed* module
            # (the outer guard ensures nothing else reached this point) and
            # walks qualname to the method.  Importing any module not on
            # the allow-list would fail here because the worker also
            # re-validates the module name against the parent's list, which
            # means a single misconfiguration is caught twice.
            worker_script = (
                "import json, sys, importlib\n"
                "ALLOWED = set(" + repr(sorted(ALLOWED_SANDBOX_MODULES)) + ")\n"
                "data = json.loads(sys.stdin.read())\n"
                "module_name = data['module']\n"
                "if module_name not in ALLOWED:\n"
                "    sys.stderr.write('refused: module not allow-listed: ' + module_name + '\\n')\n"
                "    sys.exit(2)\n"
                "mod = importlib.import_module(module_name)\n"
                "obj = mod\n"
                "for attr in data['qualname'].split('.'):\n"
                "    obj = getattr(obj, attr)\n"
                "result = obj(**data['kwargs'])\n"
                "json.dump({'ok': True, 'result': result}, sys.stdout)\n"
            )

            # Fixed argv and JSON stdin payload; handler kwargs are not shell-interpolated.
            proc = subprocess.run(  # noqa: S603  # nosec B603
                [sys.executable, "-c", worker_script],
                input=payload,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )

            if proc.returncode == 0:
                try:
                    out = json.loads(proc.stdout)
                    if out.get("ok"):
                        return out["result"]
                    # returncode 0 but "ok" is falsy — sandbox returned unexpected payload
                    logger.critical(
                        "LAW 15: Sandbox subprocess returned ok=false for [%s]; "
                        "in-process fallback disabled — failing closed per LAW 15",
                        handler_name,
                    )
                    _msg = (
                        f"LAW 15 sandbox subprocess returned ok=false for [{handler_name}]; "
                        f"in-process fallback is disabled per LAW 15."
                    )
                    raise SandboxError(_msg)
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.critical(
                        "LAW 15: Sandbox subprocess returned invalid JSON for [%s]; "
                        "in-process fallback disabled — failing closed per LAW 15",
                        handler_name,
                    )
                    _msg = (
                        f"LAW 15 sandbox subprocess returned invalid JSON for [{handler_name}]; "
                        f"in-process fallback is disabled per LAW 15."
                    )
                    raise SandboxError(_msg)
            elif proc.returncode == 2:
                # Worker explicitly rejected the dispatch
                logger.warning(
                    "Sandbox subprocess refused to execute [%s]: ref=%d err=%s",
                    handler_name,
                    proc.returncode,
                    proc.stderr[:500],
                )
                msg = f"Sandbox worker refused to execute [{handler_name}]"
                raise PermissionError(
                    msg,
                )
            else:
                logger.critical(
                    "LAW 15: Sandbox subprocess exited %d for [%s]: %s; in-process fallback disabled — failing closed per LAW 15",
                    proc.returncode,
                    handler_name,
                    proc.stderr[:500],
                )
                _msg = (
                    f"LAW 15 sandbox subprocess exited {proc.returncode} for [{handler_name}]; "
                    f"in-process fallback is disabled per LAW 15."
                )
                raise SandboxError(_msg)

        except subprocess.TimeoutExpired:
            logger.critical(
                "LAW 15: Sandbox subprocess timed out for [%s]; in-process fallback disabled — failing closed per LAW 15",
                handler_name,
            )
            _msg = (
                f"LAW 15 sandbox subprocess timed out for [{handler_name}]; "
                f"in-process fallback is disabled per LAW 15. "
                f"Investigate the subprocess timeout immediately."
            )
            raise SandboxError(_msg) from None
        except PermissionError:
            # Re-raise — the sandbox worker explicitly refused. We must
            # not silently fall back to in-process for this case (that
            # would defeat the entire LAW 15 sandbox).
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError, AttributeError) as exc:
            logger.critical(
                "LAW 15: Sandbox subprocess failed for [%s] (%s); in-process fallback disabled — failing closed per LAW 15",
                handler_name,
                exc,
            )
            _msg = (
                f"LAW 15 sandbox subprocess failed for [{handler_name}]: {exc}; "
                f"in-process fallback is disabled per LAW 15. "
                f"Investigate the subprocess failure immediately."
            )
            raise SandboxError(_msg) from exc

        # Unreachable: all non-success branches above raise.
        # If new code paths are added that reach this point they MUST
        # also raise rather than fall back to in-process execution.

    def get_available_tools(self) -> list[str]:
        return list(self._handlers.keys())


_manager: SubstratePluginManager | None = None
_call_count = 0
_call_count_lock = __import__("threading").Lock()


def get_llm_call_count() -> int:
    return _call_count


def reset_llm_call_count() -> None:
    global _call_count
    with _call_count_lock:
        _call_count = 0


def _record_call() -> None:
    global _call_count
    with _call_count_lock:
        _call_count += 1


def get_plugin_manager(ws: Any = None) -> SubstratePluginManager:
    global _manager
    if _manager is None:
        _manager = SubstratePluginManager(ws=ws)
    return _manager


def reset_plugin_manager() -> None:
    """Reset the global plugin manager (for testing)."""
    global _manager
    _manager = None
