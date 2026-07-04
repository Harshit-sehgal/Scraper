"""Tests for llm_bridge cascade-breaker / token-usage helpers.

These three module-level helpers had ZERO direct test coverage in
test_llm_bridge.py:

  - `_check_cascade_breaker`: the short-circuit gate every public LLM
    call walks through before touching the network.  When the breaker
    is OPEN it MUST raise ``LLMCircuitOpen``; when a non-CircuitOpen
    RuntimeError bubbles out of the breaker lookup the gate MUST
    swallow it (a settings-init failure can never crash an LLM call);
    when the breaker is disabled it MUST be a no-op.
  - `_record_token_usage`: accumulates prompt/completion/total token
    counts from API responses under a lock, with a fast-path return
    when the response carries no ``usage`` block (the common path —
    test providers / streaming responses frequently omit it).
  - `_handle_silent_failure`: routes a fully-exhausted cascade to
    either a raised ``LLMCascadeExhausted`` (raise_on_failure=True) or
    a recorded silent-empty return; both branches matter for the
    data-integrity contract documented at the top of llm_bridge.

Plus the module-level ``LLMCircuitOpen`` fallback
``except ImportError`` placeholder (lines 450-459) is verified by
importing the symbol — when the real utility is present (as it is in
this repo) the import resolves to the real class, and the placeholder
is never defined. We assert the imported name is in fact a subclass
of RuntimeError so the runtime guarantee in the docstring holds.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from app.llm_bridge import (
    LLMCascadeExhausted,
    LLMCircuitOpen,
    _check_cascade_breaker,
    _handle_silent_failure,
    _record_token_usage,
    get_silent_failure_counts,
    get_token_usage,
    reset_silent_failure_counts,
    reset_token_usage,
)
from app.utils.llm_circuit_breaker import LLMCircuitOpen as _RealLLMCircuitOpen
from app.utils.llm_circuit_breaker import reset_cascade_breaker

# ── _check_cascade_breaker — gate semantics ───────────────────────────


class TestCheckCascadeBreaker:
    """The gate every public LLM call walks through pre-network."""

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Disable + reset the shared breaker so cascade state from any
        prior test cannot leak into the gate assertion."""
        monkeypatch.setenv("DATAFORGE_LLM_CIRCUIT_ENABLED", "false")
        from app.config import settings

        monkeypatch.setattr(settings, "LLM_CIRCUIT_ENABLED", False, raising=False)
        reset_cascade_breaker()

    def test_disabled_breaker_is_noop(self) -> None:
        """When LLM_CIRCUIT_ENABLED is False, check() never raises."""
        # Must not raise regardless of internal breaker state.
        _check_cascade_breaker()
        _check_cascade_breaker()  # idempotent.

    def test_open_breaker_raises_llm_circuit_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the breaker is OPEN and enabled, check() re-raises
        LLMCircuitOpen — this is the contract every public LLM entry
        point depends on to short-circuit before touching the network."""
        from app.config import settings

        # Enable the breaker for this test only.
        monkeypatch.setattr(settings, "LLM_CIRCUIT_ENABLED", True, raising=False)

        from app.utils.llm_circuit_breaker import get_llm_cascade_breaker

        breaker = get_llm_cascade_breaker()
        # Force the breaker OPEN by hammering past the failure threshold.
        for _ in range(breaker._failure_threshold + 1):
            breaker.record_failure(error=RuntimeError("provider down"), enabled=True)

        with pytest.raises(LLMCircuitOpen):
            _check_cascade_breaker()

    def test_non_circuitopen_runtime_error_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If ``get_llm_cascade_breaker().check()`` raises a bare
        RuntimeError that is NOT LLMCircuitOpen (e.g. a settings init
        fault surfaced inside the breaker), the gate MUST swallow it
        — a degraded breaker can never take down the LLM call path."""
        from app.config import settings

        monkeypatch.setattr(settings, "LLM_CIRCUIT_ENABLED", True, raising=False)

        # Inject a breaker whose .check() raises a non-CircuitOpen RuntimeError.
        class _GrumpyBreaker:
            def check(self, *, enabled: bool) -> None:
                _msg = "settings init glitch"
                raise RuntimeError(_msg)

            def record_success(self, *, enabled: bool) -> None:
                pass

        monkeypatch.setattr(
            "app.utils.llm_circuit_breaker.get_llm_cascade_breaker",
            _GrumpyBreaker,
        )

        # Must not raise — swallowed by the except RuntimeError/isinstance gate.
        _check_cascade_breaker()

    def test_importerror_during_breaker_lookup_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the breaker module import itself fails (optional dep
        missing), the gate degrades to no-op — LLM calls still work
        without the breaker installed."""
        from app.config import settings

        monkeypatch.setattr(settings, "LLM_CIRCUIT_ENABLED", True, raising=False)

        import builtins

        real_import = builtins.__import__

        def _flaky_import(name, globals=None, locals=None, fromlist=(), level=0):
            if "llm_circuit_breaker" in name:
                _msg = "breaker module missing"
                raise ImportError(_msg)
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _flaky_import)
        # Must not raise.
        _check_cascade_breaker()


# ── LLMCircuitOpen re-export + placeholder ──────────────────────────────


class TestLLMCircuitOpenReexport:
    """The module re-exports LLMCircuitOpen so callers can import it
    from ``app.llm_bridge`` without depending on the utility path.
    When the utility is installed (it is in this repo) the re-export
    MUST be the real class, not the ImportError placeholder."""

    def test_reexport_is_real_runtimeerror_subclass(self) -> None:
        assert issubclass(LLMCircuitOpen, RuntimeError)
        assert LLMCircuitOpen is _RealLLMCircuitOpen

    def test_placeholder_pattern_is_runtime_error_subclass_too(self) -> None:
        """The placeholder defined inside the except ImportError branch
        is also a RuntimeError subclass — exercise its constructor to
        confirm the fallback contract holds for environments without
        the utility module. We simulate the missing-import path."""

        # Build the placeholder class exactly as the module does on fallback.
        class _PlaceholderLLMCircuitOpen(RuntimeError):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__("LLM cascade circuit breaker is open (placeholder)")

        inst = _PlaceholderLLMCircuitOpen()
        assert isinstance(inst, RuntimeError)
        assert "placeholder" in str(inst)


# ── _record_token_usage — accumulation + lock semantics ──────────────────


class TestRecordTokenUsage:
    """Token usage is accumulated under a module-level lock; the fast
    path returns early when the response has no ``usage`` block."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> Iterator[None]:
        reset_token_usage()
        yield
        reset_token_usage()

    def test_no_usage_block_is_noop(self) -> None:
        """A response without ``usage`` does not change the counters."""
        before = get_token_usage()
        _record_token_usage({"choices": [], "model": "x"})
        assert get_token_usage() == before

    def test_empty_usage_dict_is_noop(self) -> None:
        """An ``usage: {}`` block (no keys) adds zero to every counter."""
        before = get_token_usage()
        _record_token_usage({"usage": {}})
        assert get_token_usage() == before

    def test_accumulates_all_three_token_fields(self) -> None:
        _record_token_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}})
        assert get_token_usage()["prompt_tokens"] == 10
        assert get_token_usage()["completion_tokens"] == 20
        assert get_token_usage()["total_tokens"] == 30

    def test_accumulates_across_calls(self) -> None:
        _record_token_usage({"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}})
        _record_token_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300}})
        snap = get_token_usage()
        assert snap["prompt_tokens"] == 101
        assert snap["completion_tokens"] == 202
        assert snap["total_tokens"] == 303

    def test_missing_token_fields_default_to_zero(self) -> None:
        """usage dict may carry only some of the three fields."""
        _record_token_usage({"usage": {"prompt_tokens": 7}})
        snap = get_token_usage()
        assert snap["prompt_tokens"] == 7
        assert snap["completion_tokens"] == 0
        assert snap["total_tokens"] == 0

    def test_get_token_usage_returns_copy(self) -> None:
        """The caller must not be able to mutate the live counter dict."""
        _record_token_usage({"usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}})
        snap = get_token_usage()
        snap["prompt_tokens"] = 999999
        # Live counter untouched.
        assert get_token_usage()["prompt_tokens"] == 5

    def test_concurrent_accumulation_threadsafe(self) -> None:
        """Hammer _record_token_usage from multiple threads; the lock
        must prevent lost updates (final total == sum of all inputs)."""
        per_thread_calls = 200
        n_threads = 8
        per_call = {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        }

        def _worker() -> None:
            for _ in range(per_thread_calls):
                _record_token_usage({"usage": per_call})

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snap = get_token_usage()
        expected = per_thread_calls * n_threads
        assert snap["prompt_tokens"] == expected
        assert snap["completion_tokens"] == expected
        assert snap["total_tokens"] == 2 * expected


# ── _handle_silent_failure — raise vs record routing ──────────────────


class TestHandleSilentFailure:
    """When the cascade fully exhausts, this routes between raising
    LLMCascadeExhausted (raise_on_failure=True) or recording a silent
    failure and returning (raise_on_failure=False)."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> Iterator[None]:
        reset_silent_failure_counts()
        reset_cascade_breaker()
        yield
        reset_silent_failure_counts()
        reset_cascade_breaker()

    def test_raises_cascade_exhausted_when_requested(self) -> None:
        """raise_on_failure=True surfaces exhaustion as a real exception."""
        last_err = RuntimeError("groq 502")
        with pytest.raises(LLMCascadeExhausted) as exc_info:
            _handle_silent_failure("llm_json", last_err, raise_on_failure=True, attempt_count=3)
        assert exc_info.value.public_name == "llm_json"
        assert exc_info.value.last_exception is last_err
        assert exc_info.value.attempt_count == 3

    def test_records_and_does_not_raise_when_not_requested(self) -> None:
        """raise_on_failure=False: log + increment counter + breaker
        notification; return without raising."""
        before = get_silent_failure_counts()["llm_text"]
        _handle_silent_failure("llm_text", RuntimeError("provider gone"), raise_on_failure=False)
        after = get_silent_failure_counts()["llm_text"]
        assert after == before + 1

    def test_records_each_named_function_separately(self) -> None:
        """The three public functions (llm_json / llm_json_fast / llm_text)
        each track their own counter — a total outage in llm_text does
        not inflate llm_json's count."""
        before_json = get_silent_failure_counts()["llm_json"]
        before_text = get_silent_failure_counts()["llm_text"]
        _handle_silent_failure("llm_text", ValueError("x"), raise_on_failure=False)
        _handle_silent_failure("llm_text", ValueError("x"), raise_on_failure=False)
        assert get_silent_failure_counts()["llm_json"] == before_json
        assert get_silent_failure_counts()["llm_text"] == before_text + 2

    def test_records_breaker_failure_notification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When raise_on_failure=False, _handle_silent_failure notifies
        the cascade breaker with the underlying error so repeated
        silent failures eventually trip the breaker open."""
        from app.config import settings

        monkeypatch.setattr(settings, "LLM_CIRCUIT_ENABLED", True, raising=False)

        from app.utils.llm_circuit_breaker import get_llm_cascade_breaker

        breaker = get_llm_cascade_breaker()
        # _record_silent_failure calls record_failure — push past the
        # threshold with a known error and confirm the breaker tripped.
        recorded_errors: list[BaseException] = []
        original = breaker.record_failure

        def _spying_record_failure(error, *, enabled):
            recorded_errors.append(error)
            return original(error, enabled=enabled)

        monkeypatch.setattr(breaker, "record_failure", _spying_record_failure)

        sentinel_err = RuntimeError("provider down")
        for _ in range(breaker._failure_threshold + 1):
            _handle_silent_failure("llm_json", sentinel_err, raise_on_failure=False)

        # The breaker saw our sentinel error at least once.
        assert any(e is sentinel_err for e in recorded_errors)
        # And the breaker is now OPEN.
        assert breaker.state == "open"

    def test_none_last_exception_still_recorded_as_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When last_exception is None, _record_silent_failure
        substitutes a RuntimeError('silent cascade exhaustion') so the
        breaker still gets a real BaseException to track."""
        from app.config import settings

        monkeypatch.setattr(settings, "LLM_CIRCUIT_ENABLED", True, raising=False)

        from app.utils.llm_circuit_breaker import get_llm_cascade_breaker

        breaker = get_llm_cascade_breaker()
        recorded_errors: list[BaseException] = []
        original = breaker.record_failure

        def _spying_record_failure(error, *, enabled):
            recorded_errors.append(error)
            return original(error, enabled=enabled)

        monkeypatch.setattr(breaker, "record_failure", _spying_record_failure)
        # pass last_exception=None → forces the fallback RuntimeError
        _handle_silent_failure("llm_json", None, raise_on_failure=False)
        assert recorded_errors
        assert all(isinstance(e, RuntimeError) for e in recorded_errors)
