"""Tests for acquisition mode and escalation logic."""

from app.acquisition_mode import (
    AcquisitionMode,
    AcquisitionConfig,
    escalate_mode,
    should_escalate,
)


class TestAcquisitionMode:
    """Tests for AcquisitionMode enum."""

    def test_standard_mode(self):
        assert AcquisitionMode.STANDARD == "standard"

    def test_aggressive_mode(self):
        assert AcquisitionMode.AGGRESSIVE == "aggressive"

    def test_deep_scan_mode(self):
        assert AcquisitionMode.DEEP_SCAN == "deep_scan"


class TestAcquisitionConfig:
    """Tests for AcquisitionConfig.from_mode()."""

    def test_standard_config(self):
        config = AcquisitionConfig.from_mode(AcquisitionMode.STANDARD)
        assert config.attempt_recovery is False
        assert config.attempt_search_form is False
        assert config.max_retries == 1
        assert config.try_alternatives is False
        assert config.timeout_multiplier == 1.0

    def test_aggressive_config(self):
        config = AcquisitionConfig.from_mode(AcquisitionMode.AGGRESSIVE)
        assert config.attempt_recovery is True
        assert config.attempt_search_form is True
        assert config.max_retries == 2
        assert config.try_alternatives is True
        assert config.timeout_multiplier == 1.5

    def test_deep_scan_config(self):
        config = AcquisitionConfig.from_mode(AcquisitionMode.DEEP_SCAN)
        assert config.attempt_recovery is True
        assert config.attempt_search_form is True
        assert config.max_retries == 3
        assert config.try_alternatives is True
        assert config.timeout_multiplier == 2.0

    def test_all_modes_detect_session_params(self):
        for mode in AcquisitionMode:
            config = AcquisitionConfig.from_mode(mode)
            assert config.detect_session_params is True

    def test_all_modes_detect_empty_responses(self):
        for mode in AcquisitionMode:
            config = AcquisitionConfig.from_mode(mode)
            assert config.detect_empty_responses is True


class TestEscalateMode:
    """Tests for escalate_mode()."""

    def test_standard_to_aggressive(self):
        assert escalate_mode(AcquisitionMode.STANDARD) == AcquisitionMode.AGGRESSIVE

    def test_aggressive_to_deep_scan(self):
        assert escalate_mode(AcquisitionMode.AGGRESSIVE) == AcquisitionMode.DEEP_SCAN

    def test_deep_scan_stays(self):
        assert escalate_mode(AcquisitionMode.DEEP_SCAN) == AcquisitionMode.DEEP_SCAN


class TestShouldEscalate:
    """Tests for should_escalate()."""

    def test_escalate_on_session_expired(self):
        assert should_escalate(AcquisitionMode.STANDARD, "session_expired") is True

    def test_escalate_on_empty_response(self):
        assert should_escalate(AcquisitionMode.STANDARD, "direct", empty_response=True) is True

    def test_escalate_on_recovery_failed(self):
        assert should_escalate(AcquisitionMode.AGGRESSIVE, "recovery_failed") is True

    def test_escalate_on_anti_bot_blocked(self):
        assert should_escalate(AcquisitionMode.AGGRESSIVE, "anti_bot_blocked") is True

    def test_no_escalate_on_awaiting_search_params(self):
        assert should_escalate(AcquisitionMode.STANDARD, "awaiting_search_params") is False

    def test_no_escalate_on_direct(self):
        assert should_escalate(AcquisitionMode.STANDARD, "direct") is False

    def test_no_escalate_on_recovered(self):
        assert should_escalate(AcquisitionMode.STANDARD, "recovered") is False

    def test_no_escalate_at_deep_scan(self):
        assert should_escalate(AcquisitionMode.DEEP_SCAN, "session_expired") is False

    def test_no_escalate_at_deep_scan_even_with_empty(self):
        assert should_escalate(AcquisitionMode.DEEP_SCAN, "direct", empty_response=True) is False