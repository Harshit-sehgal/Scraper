"""Tests for the router-level idempotency fail-closed behavior.

The helpers in ``app.routers.jobs_state`` wrap the repository's
idempotency-key methods. This test module verifies:

1. Lookup failures increment Prometheus counters
2. Lookup failures flip to 503 after the per-window cap is exceeded
3. The streak resets on a successful lookup
4. record_idempotency_key is best-effort (logs error on failure, no raise)
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def _reset_dedup_streak():
    """Reset the module-level failure streak before each test."""
    # Import the module and reset the global counter directly
    import app.routers.jobs_state as mod

    original = mod._dedup_fail_streak
    mod._dedup_fail_streak = 0
    yield
    mod._dedup_fail_streak = original


class TestDedupLookupFailClosed:
    """Verify that repeated lookup failures eventually flip to 503."""

    def test_transient_failure_returns_none(self, monkeypatch) -> None:
        """A single lookup failure should return None (fail-open)."""
        from app.routers.jobs_state import lookup_idempotency_key

        monkeypatch.setattr(
            "app.routers.jobs_state.get_job_repository",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )
        # Should not raise — fails open for the first N failures
        result = lookup_idempotency_key("test-key")
        assert result is None

    def test_exceeding_cap_raises_503(self, monkeypatch) -> None:
        """Once the per-window failure cap is exceeded, raise 503."""
        import app.routers.jobs_state as mod

        monkeypatch.setattr(
            "app.routers.jobs_state.get_job_repository",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )
        # Fill the streak up to the cap
        cap = mod._DEDUP_FAIL_MAX_PER_WINDOW
        mod._dedup_fail_streak = cap  # Set to cap so next failure exceeds it

        with pytest.raises(HTTPException) as exc_info:
            mod.lookup_idempotency_key("over-cap-key")
        assert exc_info.value.status_code == 503
        assert "Idempotency store is unavailable" in str(exc_info.value.detail)

    def test_success_resets_streak(self, monkeypatch) -> None:
        """A successful lookup resets the failure streak to zero."""
        import app.routers.jobs_state as mod

        # Set a non-zero streak
        mod._dedup_fail_streak = 10

        # Mock a successful lookup
        class _FakeRepo:
            def lookup_idempotency_key(self, key):
                return "job-abc"

        monkeypatch.setattr(
            "app.routers.jobs_state.get_job_repository",
            _FakeRepo,
        )
        result = mod.lookup_idempotency_key("good-key")
        assert result == "job-abc"
        assert mod._dedup_fail_streak == 0

    def test_record_failure_does_not_raise(self, monkeypatch) -> None:
        """record_idempotency_key on failure does NOT raise (best-effort)."""
        from app.routers.jobs_state import record_idempotency_key

        monkeypatch.setattr(
            "app.routers.jobs_state.get_job_repository",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )
        # Must NOT raise — best-effort after job creation
        record_idempotency_key("key-x", "job-y", "fp")

    def test_fingerprint_lookup_same_streak(self, monkeypatch) -> None:
        """lookup_idempotency_fingerprint shares the same cap/streak."""
        import app.routers.jobs_state as mod

        monkeypatch.setattr(
            "app.routers.jobs_state.get_job_repository",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )
        cap = mod._DEDUP_FAIL_MAX_PER_WINDOW
        mod._dedup_fail_streak = cap

        with pytest.raises(HTTPException) as exc_info:
            mod.lookup_idempotency_fingerprint("over-cap-fp")
        assert exc_info.value.status_code == 503

    def test_prometheus_counter_incremented(self, monkeypatch) -> None:
        """Lookup failure increments dedup_lookup_miss_total."""
        from app.routers.jobs_state import lookup_idempotency_key

        monkeypatch.setattr(
            "app.routers.jobs_state.get_job_repository",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )

        recorded = []

        def fake_record():
            recorded.append(1)

        monkeypatch.setattr(
            "app.metrics_collector.record_dedup_lookup_miss",
            fake_record,
        )
        lookup_idempotency_key("key-with-metric")
        assert len(recorded) == 1
