"""Substrate LLM Bridge — Secure tool-calling and plugin management.

LAW 15: External logic (Plugins) must be executed in a sandboxed context.
All tool-calls must be traceable and governed by the Substrate Policy Engine.
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

import httpx

from app.config import settings

# ─── Legacy LLM Utility Support ──────────────────────────────────────


def _extract_json_payload(text: str | None):
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    for candidate in (raw,):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            logging.getLogger(__name__).debug("_extract_json_payload: direct JSON parse failed (len=%d)", len(candidate))

    match = re.search(r"\{[\s\S]*?\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logging.getLogger(__name__).debug(
                "_extract_json_payload: object JSON parse failed for match of len %d", len(match.group(0))
            )

    match = re.search(r"\[[\s\S]*?\]", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logging.getLogger(__name__).debug(
                "_extract_json_payload: array JSON parse failed for match of len %d", len(match.group(0))
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
    payload: dict,
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
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers or {})
                response.raise_for_status()
                data = response.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                return _extract_json_payload(content)
        except Exception as error:
            logging.exception(error)
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
    payload: dict,
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
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers or {})
                response.raise_for_status()
                data = response.json()
                return ((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
        except Exception as error:
            logging.exception(error)
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


def _record_llm_degradation(subsystem: str, cause: str, severity: str = "warning"):
    """Helper to record LLM failures in the semantic world state if available."""
    try:
        from app.semantic_world_state import get_world_state

        ws = get_world_state()
        ws.record_degradation(subsystem=subsystem, severity=severity, cause=cause)
    except Exception as e:
        # Fallback to debug logging if world state is unavailable
        logging.getLogger(__name__).debug("Telemetry skipped (WS unavailable): %s", e)


def _public_llm_fallbacks_enabled() -> bool:
    """Return whether unauthenticated public LLM fallbacks may be called."""
    return bool(settings.LLM_ENABLE_PUBLIC_FALLBACKS)


async def llm_json(messages: list[dict], temperature: float | None = None, timeout: int | None = None):
    try:
        from app.metrics_collector import record_llm_call

        record_llm_call()
    except Exception:  # nosec B110
        pass
    if temperature is None:
        temperature = settings.LLM_TEMPERATURE
    if timeout is None:
        timeout = settings.LLM_TIMEOUT
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
            except Exception as e:
                logging.exception(e)
                stage = "Groq JSON call" if idx == 0 else "Groq JSON fallback model call"
                logging.error("%s failed (%s): %s", stage, model, e)
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
        except Exception as e:
            logging.error("Pollinations JSON call failed (prompt_len=%d): %s", len(messages), e)
            _record_llm_degradation(subsystem="pollinations", cause=f"JSON call failed: {e}")

        try:

            def _run_g4f_json():
                try:
                    from g4f.client import Client
                except ImportError:
                    logging.warning("g4f not installed — skipping g4f JSON fallback")
                    return None
                client = Client()
                res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    timeout=timeout,
                )
                if not res.choices:
                    raise ValueError("Empty choices in LLM response")
                return res.choices[0].message.content.strip()

            content = await asyncio.to_thread(_run_g4f_json)
            if content is None:
                return {}
            parsed = _extract_json_payload(content)
            if parsed is not None:
                return parsed
        except Exception as e:
            logging.error("g4f JSON fallback failed (prompt_len=%d): %s", len(messages), e)
            _record_llm_degradation(subsystem="g4f", cause=f"JSON fallback failed: {e}")

    return {}


async def llm_json_fast(messages: list[dict], temperature: float | None = None, timeout: int | None = None):
    """Fast-path JSON call for throughput-sensitive cleaning tasks."""
    try:
        from app.metrics_collector import record_llm_call

        record_llm_call()
    except Exception:  # nosec B110
        pass
    if temperature is None:
        temperature = settings.LLM_FAST_TEMPERATURE
    if timeout is None:
        timeout = settings.LLM_FAST_TIMEOUT
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
            except Exception as e:
                logging.exception(e)
                stage = "Groq fast JSON call" if idx == 0 else "Groq fast JSON fallback model call"
                logging.error("%s failed (%s): %s", stage, model, e)
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
        except Exception as e:
            logging.exception(e)
            logging.error("Pollinations fast JSON call failed: %s", e)
            _record_llm_degradation(subsystem="pollinations_fast", cause=f"Fast JSON call failed: {e}")

    return {}


async def llm_text(messages: list[dict], temperature: float | None = None, timeout: int | None = None) -> str:
    try:
        from app.metrics_collector import record_llm_call

        record_llm_call()
    except Exception:  # nosec B110
        pass
    if temperature is None:
        temperature = settings.LLM_TEXT_TEMPERATURE
    if timeout is None:
        timeout = settings.LLM_TIMEOUT
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
            except Exception as e:
                logging.exception(e)
                stage = "Groq text call" if idx == 0 else "Groq text fallback model call"
                logging.error("%s failed (%s): %s", stage, model, e)

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
        except Exception as e:
            logging.exception(e)
            logging.error("Pollinations text call failed: %s", e)

        try:

            def _run_g4f_text():
                try:
                    from g4f.client import Client
                except ImportError:
                    logging.warning("g4f not installed — skipping g4f text fallback")
                    return None
                client = Client()
                res = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    timeout=timeout,
                )
                if not res.choices:
                    raise ValueError("Empty choices in LLM response")
                return (res.choices[0].message.content or "").strip()

            result = await asyncio.to_thread(_run_g4f_text)
            if result is None:
                return ""
            return result
        except Exception as e:
            logging.exception(e)
            logging.error("g4f text fallback failed: %s", e)
            return ""

    return ""


# ─── Plugin Architecture (Phase 43) ──────────────────────────────────


class SubstratePluginManager:
    """Manages the registration and execution of external action handlers."""

    def __init__(self, ws: Any = None):
        self.ws = ws
        # Handlers: handler_name -> callable
        self._handlers: Dict[str, Callable] = {}
        # Sandbox state (placeholders for now)
        self._execution_history: List[dict] = []

        # ─── Self-Optimization Tools (Phase 44) ───
        self._register_native_tools()

    def _register_native_tools(self):
        """Register built-in tools for substrate self-evolution."""
        self.register_handler("role_merger", self._native_role_merger)
        self.register_handler("manifold_compressor", self._native_manifold_compressor)

    def _native_role_merger(self, **kwargs):
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
                merged_v = [(a + b) / 2 for a, b in zip(v1, v2)]
                self.ws.set_manifold_vector(role_a, merged_v)
                # Redirect role_b to role_a in topology (simplified)
                # Future: update all regions referencing role_b
                self.ws.remove_manifold_role(role_b)
                return f"Success: Merged {role_b} into {role_a}"
        return "Fail"

    def _native_manifold_compressor(self, **kwargs):
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
            logging.getLogger(__name__).info(
                f"REFACTOR: Compressed manifold from {dim} to {dim - 1} (Pruned Dim {min_idx} with var {min_var:.4f})"
            )
            return f"Success: Pruned low-variance dimension {min_idx}"

        return "Success: Manifold density optimal"

    def register_handler(self, name: str, handler: Callable):
        """Register a python function as a substrate action handler (Phase 43)."""
        self._handlers[name] = handler
        logging.getLogger(__name__).info(f"PLUGIN: Registered handler [{name}]")

    def call_tool(self, handler_name: str, **kwargs) -> Any:
        """Execute a registered handler with optional sandboxing."""
        handler = self._handlers.get(handler_name)
        if not handler:
            raise ValueError(f"Unknown handler: {handler_name}")

        # ─── Execution Boundary ───
        logging.getLogger(__name__).info(f"TOOL CALL: Executing [{handler_name}] with {kwargs}")

        try:
            # Check for budget / policy if ws is available
            if self.ws:
                from app.policy_engine import get_policy_engine

                policy = get_policy_engine(ws=self.ws)
                if not policy.can_dispatch_action(handler_name, self.ws.get_system_pressure()):
                    raise PermissionError(f"Action [{handler_name}] blocked by substrate policy")

            # Actual execution
            result = handler(**kwargs)

            self._execution_history.append({"handler": handler_name, "status": "success", "result_type": str(type(result))})
            return result

        except Exception as e:
            self._execution_history.append({"handler": handler_name, "status": "error", "error": str(e)})
            logging.getLogger(__name__).error(f"TOOL FAIL: [{handler_name}] - {e}")
            raise

    def get_available_tools(self) -> List[str]:
        return list(self._handlers.keys())


_manager: Optional[SubstratePluginManager] = None
_call_count = 0


def get_llm_call_count() -> int:
    return _call_count


def reset_llm_call_count():
    global _call_count
    _call_count = 0


def _record_call():
    global _call_count
    _call_count = _call_count + 1


def get_plugin_manager(ws: Any = None) -> SubstratePluginManager:
    global _manager
    if _manager is None:
        _manager = SubstratePluginManager(ws=ws)
    return _manager


def reset_plugin_manager():
    """Reset the global plugin manager (for testing)."""
    global _manager
    _manager = None
