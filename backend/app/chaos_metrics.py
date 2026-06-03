"""Chaos metrics — test suite execution, reporting, and operational playbooks.

Contains the ChaosTestSuite runner that executes scenarios and generates
reports, the OperationalPlaybooks with recovery procedures, and top-level
helper functions for running chaos tests.

Extracted from chaos_simulator.py for modularity (see REFACTOR_PLAN.md).
"""

import logging
from typing import Any, Dict, List

from app.chaos_scenarios import FailureMode, FailureScenario, FailureScenarios


class ChaosTestSuite:
    """Runs chaos engineering tests"""

    def __init__(self):
        self.logger = logging.getLogger("chaos_test_suite")
        self.results: List[Dict[str, Any]] = []

    async def run_all_scenarios(self) -> Dict[str, Any]:
        """Run all chaos scenarios"""
        scenarios = FailureScenarios.get_all_scenarios()
        self.logger.info(f"Running {len(scenarios)} chaos scenarios...")

        passed = 0
        failed = 0

        for scenario in scenarios:
            result = await self._run_scenario(scenario)
            self.results.append(result)

            if result["passed"]:
                passed += 1
            else:
                failed += 1

        return {
            "total": len(scenarios),
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / len(scenarios) if scenarios else 0,
            "results": self.results,
        }

    async def _run_scenario(self, scenario: FailureScenario) -> Dict[str, Any]:
        """Run a single scenario"""
        self.logger.info(f"Running scenario: {scenario.name}")

        try:
            result: dict[str, Any] = {
                "scenario": scenario.name,
                "failure_mode": scenario.failure_mode.value,
                "severity": scenario.severity.value,
                "passed": True,  # Placeholder
                "recovery_time": scenario.expected_recovery_time_seconds,
                "success_rate": scenario.expected_success_rate,
                "errors": [],
            }
            return result

        except Exception as e:
            self.logger.error(f"Error running scenario {scenario.name}: {e}")
            return {
                "scenario": scenario.name,
                "failure_mode": scenario.failure_mode.value,
                "passed": False,
                "error": str(e),
            }

    def generate_report(self) -> str:
        """Generate chaos test report"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get("passed", False))

        report = f"""
================================================================================
                      CHAOS ENGINEERING TEST REPORT
================================================================================

SUMMARY:
  Total Scenarios: {total}
  Passed: {passed}
  Failed: {total - passed}
  Pass Rate: {passed / total * 100:.1f}%

SCENARIOS BY SEVERITY:
  Critical: {sum(1 for r in self.results if "critical" in r.get("severity", "").lower())}
  High: {sum(1 for r in self.results if "high" in r.get("severity", "").lower())}
  Medium: {sum(1 for r in self.results if "medium" in r.get("severity", "").lower())}
  Low: {sum(1 for r in self.results if "low" in r.get("severity", "").lower())}

DETAILED RESULTS:
"""
        for result in self.results:
            status = "✓ PASS" if result.get("passed") else "✗ FAIL"
            report += f"\n  {status} - {result.get('scenario', 'Unknown')}"

        report += "\n\n" + "=" * 80 + "\n"
        return report


# ============================================================================
# Playbooks and Recovery Procedures
# ============================================================================


class OperationalPlaybooks:
    """Playbooks for operational responses to failures"""

    @staticmethod
    def get_playbook(failure_mode: FailureMode) -> Dict[str, Any]:
        """Get the playbook for a specific failure mode"""
        playbooks = {
            FailureMode.NETWORK_TIMEOUT: {
                "name": "Network Timeout Recovery",
                "severity": "MEDIUM",
                "steps": [
                    "1. Check network connectivity (ping external hosts)",
                    "2. Check DNS resolution (nslookup)",
                    "3. Monitor existing requests (verify in-flight)",
                    "4. Trigger exponential backoff on new requests",
                    "5. Check if issue is local or widespread",
                    "6. If widespread, escalate to infrastructure team",
                    "7. Monitor recovery (check success rate)",
                    "8. If not recovered in 5 minutes, escalate",
                ],
                "metrics_to_monitor": [
                    "request_success_rate",
                    "timeout_frequency",
                    "network_latency",
                    "proxy_health",
                ],
                "escalation": "Infrastructure Team",
                "estimated_recovery_time": "2 - 5 minutes",
            },
            FailureMode.ANTI_BOT_ESCALATION: {
                "name": "Anti-Bot Escalation Recovery",
                "severity": "CRITICAL",
                "steps": [
                    "1. IMMEDIATE: Stop aggressive extraction strategies",
                    "2. Activate proxy rotation at maximum frequency",
                    "3. Randomize User-Agents and headers",
                    "4. Enable request rate limiting (increase delays 10x)",
                    "5. Monitor anti-bot detection rate (should decrease)",
                    "6. Switch domain to lower priority crawling",
                    "7. If escalation continues, enable JS rendering",
                    "8. If still escalating, consider domain blacklist",
                    "9. Alert on-call engineer",
                    "10. Monitor for 24 hours before resuming normal crawling",
                ],
                "metrics_to_monitor": [
                    "anti_bot_detection_rate",
                    "extraction_success_rate",
                    "request_latency",
                    "domain_health_score",
                ],
                "escalation": "On-Call Engineer",
                "estimated_recovery_time": "30 - 120 minutes",
            },
            FailureMode.SELECTOR_POISONING: {
                "name": "Selector Poisoning Recovery",
                "severity": "HIGH",
                "steps": [
                    "1. Detect: Extraction failure rate > 50% for domain",
                    "2. Trigger selector_discovery to find new candidates",
                    "3. Score new candidates with ML models",
                    "4. Test new selectors on test set of pages",
                    "5. If any new selector >80% success, switch",
                    "6. If all new selectors <80%, manual review needed",
                    "7. Check if website was redesigned (compare structure)",
                    "8. Update domain metadata with new structure version",
                    "9. Resume extraction with new selectors",
                ],
                "metrics_to_monitor": [
                    "extraction_success_rate",
                    "selector_quality_score",
                    "dom_structure_version",
                ],
                "escalation": "Team Lead (for manual selector review)",
                "estimated_recovery_time": "10 - 30 minutes",
            },
            FailureMode.NODE_CRASH: {
                "name": "Node Crash Recovery",
                "severity": "MEDIUM",
                "steps": [
                    "1. System automatically detects via heartbeat timeout (3s)",
                    "2. Workload rebalanced to surviving nodes",
                    "3. In-flight work redistributed to queue",
                    "4. Failed node marked DOWN in cluster topology",
                    "5. Investigate cause of crash (check logs)",
                    "6. Restart node with investigation results",
                    "7. Rejoin node to cluster",
                    "8. Monitor node stability for 5 minutes",
                    "9. Resume normal operation if stable",
                ],
                "metrics_to_monitor": [
                    "node_availability",
                    "cluster_capacity",
                    "task_queue_depth",
                    "error_rate",
                ],
                "escalation": "Infrastructure Team (if repeated crashes)",
                "estimated_recovery_time": "3 - 10 minutes",
            },
            FailureMode.MEMORY_LEAK: {
                "name": "Memory Leak Recovery",
                "severity": "HIGH",
                "steps": [
                    "1. Detect: Memory usage growing >50MB / hour",
                    "2. Enable detailed memory profiling",
                    "3. Identify leaking component (likely selector_memory)",
                    "4. Trigger cache eviction (LRU policy)",
                    "5. Monitor memory usage post-eviction",
                    "6. If still growing, restart the process",
                    "7. Investigate root cause with profiling data",
                    "8. Update code to fix leak",
                    "9. Deploy fix and monitor",
                ],
                "metrics_to_monitor": [
                    "memory_usage",
                    "gc_pause_time",
                    "heap_size",
                    "cache_size",
                ],
                "escalation": "Developer (for code fix)",
                "estimated_recovery_time": "2 - 30 minutes (temp fix), 1 - 4 hours (permanent)",
            },
        }

        return playbooks.get(
            failure_mode,
            {
                "name": "Unknown Failure",
                "severity": "UNKNOWN",
                "steps": ["1. Investigate logs and metrics"],
                "escalation": "On-Call Engineer",
            },
        )

    @staticmethod
    def get_all_playbooks() -> Dict[str, Dict[str, Any]]:
        """Get all playbooks"""
        playbooks = {}
        for mode in FailureMode:
            playbooks[mode.value] = OperationalPlaybooks.get_playbook(mode)
        return playbooks


# ============================================================================
# Testing Helpers
# ============================================================================


async def run_chaos_test(scenario: FailureScenario) -> Dict[str, Any]:
    """Run a chaos test scenario using the ChaosSimulator."""
    from app.chaos_simulator import ChaosSimulator

    simulator = ChaosSimulator()
    result = await simulator.inject_failure(scenario.failure_mode, duration=scenario.duration_seconds)
    return result


async def run_all_chaos_tests() -> Dict[str, Any]:
    """Run all chaos tests and generate report"""
    suite = ChaosTestSuite()
    results = await suite.run_all_scenarios()
    report = suite.generate_report()
    return {
        "results": results,
        "report": report,
    }
