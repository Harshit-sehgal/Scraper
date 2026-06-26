"""Unit tests for app.chaos_metrics — ChaosTestSuite, OperationalPlaybooks, helpers."""

import pytest
from app.chaos_metrics import ChaosTestSuite, OperationalPlaybooks, run_all_chaos_tests
from app.chaos_scenarios import FailureMode, FailureScenario, SeverityLevel

# ── ChaosTestSuite ───────────────────────────────────────────────────────


class TestChaosTestSuite:
    @pytest.mark.asyncio
    async def test_run_all_scenarios_returns_summary(self):
        suite = ChaosTestSuite()
        result = await suite.run_all_scenarios()
        assert "total" in result
        assert "passed" in result
        assert "failed" in result
        assert "pass_rate" in result
        assert "results" in result
        assert result["total"] == result["passed"] + result["failed"]
        assert result["total"] > 0

    @pytest.mark.asyncio
    async def test_run_scenario_returns_expected_fields(self):
        suite = ChaosTestSuite()
        scenario = FailureScenario(
            name="test_scenario",
            description="Test network timeout scenario",
            failure_mode=FailureMode.NETWORK_TIMEOUT,
            severity=SeverityLevel.MEDIUM,
            duration_seconds=5,
            expected_impact="Requests fail with timeout",
            expected_recovery_time_seconds=10,
            expected_success_rate=0.9,
            triggers=["network delay"],
            recovery_actions=["retry"],
            validation_checks=["check latency"],
        )
        result = await suite._run_scenario(scenario)
        assert result["scenario"] == "test_scenario"
        assert result["failure_mode"] == "network_timeout"
        assert result["severity"] == "medium"
        assert result["passed"] is True
        assert result["recovery_time"] == 10
        assert result["success_rate"] == 0.9

    def test_generate_report_single(self):
        suite = ChaosTestSuite()
        suite.results = [
            {"scenario": "solo", "passed": True, "severity": "low"},
        ]
        report = suite.generate_report()
        assert "CHAOS ENGINEERING TEST REPORT" in report
        assert "Total Scenarios: 1" in report
        assert "Passed: 1" in report
        assert "Failed: 0" in report

    def test_generate_report_with_results(self):
        suite = ChaosTestSuite()
        suite.results = [
            {"scenario": "s1", "passed": True, "severity": "critical"},
            {"scenario": "s2", "passed": False, "severity": "high"},
            {"scenario": "s3", "passed": True, "severity": "medium"},
            {"scenario": "s4", "passed": True, "severity": "low"},
        ]
        report = suite.generate_report()
        assert "Total Scenarios: 4" in report
        assert "Passed: 3" in report
        assert "Failed: 1" in report
        assert "75.0%" in report
        assert "Critical: 1" in report
        assert "High: 1" in report
        assert "PASS" in report
        assert "FAIL" in report

    @pytest.mark.asyncio
    async def test_results_accumulate(self):
        suite = ChaosTestSuite()
        await suite.run_all_scenarios()
        assert len(suite.results) > 0
        first_count = len(suite.results)
        await suite.run_all_scenarios()
        assert len(suite.results) == first_count * 2


# ── OperationalPlaybooks ─────────────────────────────────────────────────


class TestOperationalPlaybooks:
    def test_known_playbook(self):
        pb = OperationalPlaybooks.get_playbook(FailureMode.NETWORK_TIMEOUT)
        assert pb["name"] == "Network Timeout Recovery"
        assert pb["severity"] == "MEDIUM"
        assert len(pb["steps"]) > 0
        assert "metrics_to_monitor" in pb
        assert "escalation" in pb

    def test_anti_bot_playbook(self):
        pb = OperationalPlaybooks.get_playbook(FailureMode.ANTI_BOT_ESCALATION)
        assert pb["severity"] == "CRITICAL"
        assert len(pb["steps"]) >= 5

    def test_selector_poisoning_playbook(self):
        pb = OperationalPlaybooks.get_playbook(FailureMode.SELECTOR_POISONING)
        assert pb["severity"] == "HIGH"

    def test_node_crash_playbook(self):
        pb = OperationalPlaybooks.get_playbook(FailureMode.NODE_CRASH)
        assert pb["severity"] == "MEDIUM"

    def test_memory_leak_playbook(self):
        pb = OperationalPlaybooks.get_playbook(FailureMode.MEMORY_LEAK)
        assert pb["severity"] == "HIGH"

    def test_unknown_failure_mode_fallback(self):
        pb = OperationalPlaybooks.get_playbook(FailureMode.GOSSIP_FAILURE)
        assert pb["name"] == "Unknown Failure"
        assert pb["severity"] == "UNKNOWN"

    def test_get_all_playbooks(self):
        all_pbs = OperationalPlaybooks.get_all_playbooks()
        assert isinstance(all_pbs, dict)
        assert len(all_pbs) == len(FailureMode)
        for mode in FailureMode:
            assert mode.value in all_pbs


# ── Top-level helpers ────────────────────────────────────────────────────


class TestHelpers:
    @pytest.mark.asyncio
    async def test_run_all_chaos_tests(self):
        result = await run_all_chaos_tests()
        assert "results" in result
        assert "report" in result
        assert isinstance(result["report"], str)
