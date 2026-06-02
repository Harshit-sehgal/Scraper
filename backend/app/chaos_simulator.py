"""
DataForge Chaos Engineering Framework
Phase 5 Week 5 - 8: Test system resilience and validate recovery

This module provides failure injection and chaos testing capabilities to ensure
the system remains operational under adverse conditions.

Failure Categories:
  1. Fetch Layer Failures (network, proxies, browsers)
  2. Extract Layer Failures (selectors, parsing, extraction)
  3. Memory / State Failures (cache, persistence, data loss)
  4. Intelligence Layer Failures (orchestration, decision-making)
  5. Distributed System Failures (node crashes, network partitions)
  6. Recovery Mechanism Failures (cascading failures, exhaustion)

The core types (FailureMode, SeverityLevel, FailureScenario) and scenario
collection (FailureScenarios) are defined in chaos_scenarios.py.
The test suite runner (ChaosTestSuite) and playbooks (OperationalPlaybooks)
are in chaos_metrics.py.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

# Import symbols used directly in this file
from app.chaos_scenarios import FailureMode, FailureScenarios


# Backward-compatible re-exports via __getattr__ (for names not used directly in this file)
# so pyflakes does not flag unused-import warnings.
def __getattr__(name):
    import app.chaos_metrics as _cm
    import app.chaos_scenarios as _cs

    _re_exports = {
        "SeverityLevel": _cs,
        "FailureScenario": _cs,
        "ChaosTestSuite": _cm,
        "OperationalPlaybooks": _cm,
        "run_chaos_test": _cm,
        "run_all_chaos_tests": _cm,
    }
    if name in _re_exports:
        return getattr(_re_exports[name], name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============================================================================
# Chaos Simulator
# ============================================================================


class ChaosSimulator:
    """Main chaos engineering simulator"""

    def __init__(self, system_interface=None):
        """
        Initialize chaos simulator

        Args:
            system_interface: Interface to the system being tested
                             Allows injection of failures and observation
        """
        self.system = system_interface
        self.active_failures: Dict[str, bool] = {}
        self.failure_history: List[Dict[str, Any]] = []
        self.recovery_metrics: Dict[str, Dict[str, float]] = {}
        self.logger = logging.getLogger("chaos_simulator")

    async def inject_failure(self, failure_mode: FailureMode, duration: float = 10.0, intensity: float = 1.0) -> Dict[str, Any]:
        """
        Inject a failure into the system

        Args:
            failure_mode: Type of failure to inject
            duration: How long to maintain the failure (seconds)
            intensity: Intensity of failure (0.0 - 1.0)

        Returns:
            Metrics about the failure and recovery
        """
        self.logger.info(f"Injecting failure: {failure_mode.value}")

        failure_start = time.time()
        impact_metrics = {
            "failure_mode": failure_mode.value,
            "start_time": failure_start,
            "duration": duration,
            "intensity": intensity,
            "recovered": False,
            "recovery_time": None,
            "errors_during_failure": 0,
            "successes_during_failure": 0,
        }

        self.active_failures[failure_mode.value] = True

        try:
            await asyncio.sleep(duration)
            self.active_failures[failure_mode.value] = False
            recovery_start = time.time()
            recovered = await self._wait_for_recovery(failure_mode, timeout=60.0)
            recovery_time = time.time() - recovery_start
            impact_metrics["recovered"] = recovered
            impact_metrics["recovery_time"] = recovery_time
        except Exception as e:
            self.logger.error(f"Error during chaos injection: {e}")
            impact_metrics["error"] = str(e)

        self.failure_history.append(impact_metrics)
        return impact_metrics

    async def _wait_for_recovery(self, failure_mode: FailureMode, timeout: float = 60.0) -> bool:
        """Wait for system to recover from failure"""
        start = time.time()
        while time.time() - start < timeout:
            if self._is_system_healthy(failure_mode):
                self.logger.info(f"System recovered from {failure_mode.value}")
                return True
            await asyncio.sleep(0.5)
        self.logger.error(f"System did not recover from {failure_mode.value} within {timeout}s")
        return False

    def _is_system_healthy(self, _previous_failure: FailureMode) -> bool:
        """Check if system is healthy after failure"""
        try:
            from app.domain_health_alerts import get_domain_health_monitor

            monitor = get_domain_health_monitor()
            if self.system and hasattr(self.system, "current_url"):
                url = self.system.current_url
                if url:
                    domain_health = monitor.get_domain_health(url)
                    if domain_health:
                        return domain_health.get("health_level") == "healthy"
            healths = monitor.get_all_domains_health()
            if not healths:
                return True
            for h in healths:
                if h.get("health_level") in ["unhealthy", "critical", "blacklisted"]:
                    return False
            return True
        except Exception as e:
            self.logger.error(f"Error checking system health: {e}")
            return True

    def is_failure_active(self, failure_mode: FailureMode) -> bool:
        """Check if a specific failure mode is currently active"""
        return self.active_failures.get(failure_mode.value, False)


_simulator: Optional["ChaosSimulator"] = None


def get_chaos_simulator() -> ChaosSimulator:
    """Get the global chaos simulator."""
    global _simulator
    if _simulator is None:
        _simulator = ChaosSimulator()
    return _simulator


if __name__ == "__main__":
    # Print all scenarios
    print("DataForge Chaos Engineering Scenarios:")
    print("=" * 80)

    scenarios = FailureScenarios.get_all_scenarios()

    categories: dict[str, list[Any]] = {}
    for scenario in scenarios:
        cat = scenario.failure_mode.value.split("_")[0]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(scenario)

    for cat, scenarios_in_cat in sorted(categories.items()):
        print(f"\n{cat.upper()} FAILURES ({len(scenarios_in_cat)} scenarios):")
        for scenario in scenarios_in_cat:
            print(f"  - {scenario.name}")
            print(f"    Severity: {scenario.severity.value}")
            print(f"    Expected Recovery: {scenario.expected_recovery_time_seconds}s")
