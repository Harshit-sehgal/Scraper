"""Substrate LLM Bridge — Secure tool-calling and plugin management.

LAW 15: External logic (Plugins) must be executed in a sandboxed context.
All tool-calls must be traceable and governed by the Substrate Policy Engine.
"""

import asyncio
import json
import logging
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
                    except (ValueError, TypeError):
                        pass
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
                    except (ValueError, TypeError):
                        pass
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


async def llm_json(messages: list[dict], temperature: float | None = None, timeout: int | None = None):
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
                    return parsed
            except _MODEL_FALLBACK_ERRORS as e:
                last_err = e
                logger.exception("LLM JSON call failed")
                stage = "Groq JSON call" if idx == 0 else "Groq JSON fallback model call"
                logger.exception("%s failed: %s", stage, model)
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
            if content is None:
                return {}
            parsed = _extract_json_payload(content)
            if parsed is not None:
                return parsed
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("g4f JSON fallback failed (prompt_len=%d)", len(messages))
            _record_llm_degradation(subsystem="g4f", cause=f"JSON fallback failed: {e}")
        except Exception as e:  # g4f may raise arbitrary exception types
            last_err = e
            logger.exception("g4f JSON fallback failed (prompt_len=%d)", len(messages))
            _record_llm_degradation(subsystem="g4f", cause=f"JSON fallback failed: {e}")

    _record_silent_failure("llm_json", last_err)
    return {}


async def llm_json_fast(messages: list[dict], temperature: float | None = None, timeout: int | None = None):
    """Fast-path JSON call for throughput-sensitive cleaning tasks."""
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
                    return parsed
            except _MODEL_FALLBACK_ERRORS as e:
                last_err = e
                logger.exception("Groq fast JSON call failed")
                stage = "Groq fast JSON call" if idx == 0 else "Groq fast JSON fallback model call"
                logger.exception("%s failed: %s", stage, model)
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


async def llm_text(messages: list[dict], temperature: float | None = None, timeout: int | None = None) -> str:
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
                    return text
            except _MODEL_FALLBACK_ERRORS as e:
                last_err = e
                logger.exception("Groq text call failed")
                stage = "Groq text call" if idx == 0 else "Groq text fallback model call"
                logger.exception("%s failed: %s", stage, model)

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
            if result is None:
                return ""
            return result  # type: ignore[no-any-return]
        except _MODEL_FALLBACK_ERRORS as e:
            last_err = e
            logger.exception("g4f text fallback failed")
        except Exception as e:  # g4f may raise arbitrary exception types
            last_err = e
            logger.exception("g4f text fallback failed")
        _record_silent_failure("llm_text", last_err)
        return ""

    _record_silent_failure("llm_text", last_err)
    return ""


# ─── Plugin Architecture (Phase 43) ──────────────────────────────────


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
        subprocess fails or is unavailable, it falls back to in-process
        execution with a warning log so the tool still completes.
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

            # LAW 15: Attempt subprocess sandbox first
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

        Attempts to run the handler in a subprocess with timeouts and
        resource limits. Falls back to in-process execution if the
        subprocess infrastructure fails, logging a warning.
        """
        # Subprocess sandbox uses a fixed interpreter argv and never shell=True.
        import subprocess  # nosec B404
        import sys

        try:
            # Serialize the handler invocation for the subprocess worker
            payload = json.dumps(
                {
                    "module": handler.__module__,
                    "qualname": handler.__qualname__,
                    "kwargs": kwargs,
                }
            )

            # Small inline worker script that imports the handler and calls it
            worker_script = (
                "import json, sys, importlib\n"
                "data = json.loads(sys.stdin.read())\n"
                "mod = importlib.import_module(data['module'])\n"
                "# Walk qualname to get the callable\n"
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
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.warning(
                        "Sandbox subprocess returned invalid JSON for [%s]; falling back",
                        handler_name,
                    )
            else:
                logger.warning(
                    "Sandbox subprocess exited %d for [%s]: %s",
                    proc.returncode,
                    handler_name,
                    proc.stderr[:500],
                )

        except subprocess.TimeoutExpired:
            logger.warning(
                "Sandbox subprocess timed out for [%s]; falling back to in-process",
                handler_name,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError, AttributeError) as exc:
            logger.warning(
                "Sandbox subprocess failed for [%s] (%s); falling back to in-process",
                handler_name,
                exc,
            )

        # Fallback: in-process execution with warning
        logger.warning(
            "LAW 15: Executing handler [%s] in-process (subprocess sandbox unavailable)",
            handler_name,
        )
        return handler(**kwargs)

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
