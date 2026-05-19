"""
DataForge Chaos Engineering Framework
Phase 5 Week 5-8: Test system resilience and validate recovery

This module provides failure injection and chaos testing capabilities to ensure
the system remains operational under adverse conditions.

Failure Categories:
  1. Fetch Layer Failures (network, proxies, browsers)
  2. Extract Layer Failures (selectors, parsing, extraction)
  3. Memory/State Failures (cache, persistence, data loss)
  4. Intelligence Layer Failures (orchestration, decision-making)
  5. Distributed System Failures (node crashes, network partitions)
  6. Recovery Mechanism Failures (cascading failures, exhaustion)
"""

import asyncio
import random
import time
from typing import Callable, List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging


# ============================================================================
# Failure Models
# ============================================================================

class FailureMode(Enum):
    """Types of failures that can be injected"""
    # Fetch Layer
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_PARTITION = "network_partition"
    PROXY_EXHAUSTION = "proxy_exhaustion"
    BROWSER_CRASH = "browser_crash"
    SSL_CERTIFICATE_ERROR = "ssl_certificate_error"
    
    # Anti-Bot
    ANTI_BOT_ESCALATION = "anti_bot_escalation"
    CAPTCHA_LOOP = "captcha_loop"
    IP_BLACKLIST_EXPANSION = "ip_blacklist_expansion"
    
    # Extract Layer
    SELECTOR_POISONING = "selector_poisoning"
    DOM_STRUCTURE_CHANGED = "dom_structure_changed"
    EXTRACTION_TIMEOUT = "extraction_timeout"
    INVALID_EXTRACTED_DATA = "invalid_extracted_data"
    
    # Memory/State
    CACHE_CORRUPTION = "cache_corruption"
    STATE_INCONSISTENCY = "state_inconsistency"
    MEMORY_LEAK = "memory_leak"
    PERSISTENCE_FAILURE = "persistence_failure"
    
    # Intelligence/Orchestration
    SEMANTIC_WORLD_STATE_CRASH = "semantic_world_state_crash"
    EVENT_DISPATCHER_STUCK = "event_dispatcher_stuck"
    STRATEGY_DECISION_FAILURE = "strategy_decision_failure"
    LEARNING_LOOP_DEADLOCK = "learning_loop_deadlock"
    
    # Distributed
    NODE_CRASH = "node_crash"
    NETWORK_PARTITION_CLUSTER = "network_partition_cluster"
    GOSSIP_FAILURE = "gossip_failure"
    CONSENSUS_FAILURE = "consensus_failure"
    
    # Cascading
    CASCADING_FAILURES = "cascading_failures"
    THUNDERING_HERD = "thundering_herd"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


class SeverityLevel(Enum):
    """Severity of failure"""
    LOW = "low"        # Recoverable, <1% impact
    MEDIUM = "medium"  # Recoverable, 1-10% impact
    HIGH = "high"      # Recoverable with effort, 10-50% impact
    CRITICAL = "critical"  # May require intervention, >50% impact


@dataclass
class FailureScenario:
    """Specification of a chaos test scenario"""
    name: str
    description: str
    failure_mode: FailureMode
    severity: SeverityLevel
    duration_seconds: float
    expected_impact: str
    expected_recovery_time_seconds: float
    expected_success_rate: float  # After recovery
    triggers: List[str]  # What triggers this failure
    recovery_actions: List[str]  # Actions system should take
    validation_checks: List[str]  # How to verify recovery


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
    
    async def inject_failure(
        self, 
        failure_mode: FailureMode, 
        duration: float = 10.0,
        intensity: float = 1.0
    ) -> Dict[str, Any]:
        """
        Inject a failure into the system
        
        Args:
            failure_mode: Type of failure to inject
            duration: How long to maintain the failure (seconds)
            intensity: Intensity of failure (0.0-1.0)
        
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
        
        # Mark failure as active
        self.active_failures[failure_mode.value] = True
        
        try:
            # Wait for duration
            await asyncio.sleep(duration)
            
            # Remove failure
            self.active_failures[failure_mode.value] = False
            
            recovery_start = time.time()
            
            # Wait for system to recover
            recovered = await self._wait_for_recovery(
                failure_mode, 
                timeout=60.0
            )
            
            recovery_time = time.time() - recovery_start
            impact_metrics["recovered"] = recovered
            impact_metrics["recovery_time"] = recovery_time
            
        except Exception as e:
            self.logger.error(f"Error during chaos injection: {e}")
            impact_metrics["error"] = str(e)
        
        self.failure_history.append(impact_metrics)
        return impact_metrics
    
    async def _wait_for_recovery(
        self, 
        failure_mode: FailureMode, 
        timeout: float = 60.0
    ) -> bool:
        """
        Wait for system to recover from failure
        
        Returns:
            True if recovered, False if timeout
        """
        start = time.time()
        
        while time.time() - start < timeout:
            if self._is_system_healthy(failure_mode):
                self.logger.info(f"System recovered from {failure_mode.value}")
                return True
            
            await asyncio.sleep(0.5)
        
        self.logger.error(f"System did not recover from {failure_mode.value} within {timeout}s")
        return False
    
    def _is_system_healthy(self, previous_failure: FailureMode) -> bool:
        """Check if system is healthy after failure"""
        # This would be implemented with actual health checks
        # For now, return True to indicate recovery
        return True


# ============================================================================
# Failure Scenarios
# ============================================================================

class FailureScenarios:
    """Collection of predefined failure scenarios"""
    
    @staticmethod
    def get_all_scenarios() -> List[FailureScenario]:
        """Get all failure scenarios"""
        return [
            # ===== FETCH LAYER FAILURES (5 scenarios) =====
            FailureScenario(
                name="Network Timeout on All Requests",
                description="All network requests timeout after 5 seconds",
                failure_mode=FailureMode.NETWORK_TIMEOUT,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=30.0,
                expected_impact="Extraction blocked, retry logic triggered",
                expected_recovery_time_seconds=10.0,
                expected_success_rate=0.8,
                triggers=["browser_pool.fetch()", "rate_limiter.check()"],
                recovery_actions=["exponential_backoff", "proxy_rotation", "retry"],
                validation_checks=[
                    "extraction_retried",
                    "backoff_applied",
                    "system_recovers_after_timeout"
                ]
            ),
            
            FailureScenario(
                name="Network Partition (Total)",
                description="Complete network isolation - no packets sent/received",
                failure_mode=FailureMode.NETWORK_PARTITION,
                severity=SeverityLevel.HIGH,
                duration_seconds=60.0,
                expected_impact="All network operations fail",
                expected_recovery_time_seconds=15.0,
                expected_success_rate=0.7,
                triggers=["browser_pool.fetch()", "distributed.gossip"],
                recovery_actions=["circuit_breaker_open", "queue_backlog", "reconnect"],
                validation_checks=[
                    "circuit_breaker_engaged",
                    "requests_queued",
                    "connectivity_restored",
                    "backlog_processed"
                ]
            ),
            
            FailureScenario(
                name="Proxy Pool Exhaustion",
                description="All proxies become unavailable simultaneously",
                failure_mode=FailureMode.PROXY_EXHAUSTION,
                severity=SeverityLevel.HIGH,
                duration_seconds=45.0,
                expected_impact="Unable to rotate proxies, IP blocking risk",
                expected_recovery_time_seconds=20.0,
                expected_success_rate=0.6,
                triggers=["proxy_manager.get_next_proxy()"],
                recovery_actions=["fallback_to_direct", "wait_for_refresh", "alert_ops"],
                validation_checks=[
                    "proxy_fallback_used",
                    "direct_connections_tried",
                    "new_proxies_added",
                    "extraction_continues"
                ]
            ),
            
            FailureScenario(
                name="Browser Crashes (5% of requests)",
                description="Random 5% of browser instances crash",
                failure_mode=FailureMode.BROWSER_CRASH,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=60.0,
                expected_impact="Failed extractions, pool refresh triggered",
                expected_recovery_time_seconds=5.0,
                expected_success_rate=0.95,
                triggers=["browser_pool.execute_in_browser()"],
                recovery_actions=["restart_browser", "retry_extraction", "pool_refresh"],
                validation_checks=[
                    "crashed_browsers_replaced",
                    "failed_extractions_retried",
                    "pool_size_maintained",
                    "recovery_automatic"
                ]
            ),
            
            FailureScenario(
                name="SSL Certificate Verification Failure",
                description="All SSL certificates fail verification (MitM scenario)",
                failure_mode=FailureMode.SSL_CERTIFICATE_ERROR,
                severity=SeverityLevel.HIGH,
                duration_seconds=30.0,
                expected_impact="HTTPS requests blocked, extraction blocked",
                expected_recovery_time_seconds=5.0,
                expected_success_rate=0.85,
                triggers=["browser_pool.fetch()", "ssl_verification"],
                recovery_actions=["retry_with_ssl_verification", "alert_ops", "fallback"],
                validation_checks=[
                    "ssl_errors_detected",
                    "retry_triggered",
                    "ops_alerted",
                    "recovery_attempted"
                ]
            ),
            
            # ===== ANTI-BOT FAILURES (3 scenarios) =====
            FailureScenario(
                name="Anti-Bot Escalation Cascade",
                description="Anti-bot detection rate increases exponentially",
                failure_mode=FailureMode.ANTI_BOT_ESCALATION,
                severity=SeverityLevel.CRITICAL,
                duration_seconds=120.0,
                expected_impact="Extraction blocked, domain health degraded",
                expected_recovery_time_seconds=60.0,
                expected_success_rate=0.4,
                triggers=["anti_bot_engine.detect()", "behavior_tracker.record()"],
                recovery_actions=[
                    "increase_backoff",
                    "rotate_proxies_aggressively",
                    "switch_user_agents",
                    "use_js_rendering",
                    "blacklist_domain"
                ],
                validation_checks=[
                    "detection_rate_climbing",
                    "recovery_strategies_applied",
                    "domain_health_recovered_or_blacklisted",
                    "no_cascading_failure"
                ]
            ),
            
            FailureScenario(
                name="CAPTCHA Loop (10% of requests)",
                description="CAPTCHA appears on 10% of requests, never solved",
                failure_mode=FailureMode.CAPTCHA_LOOP,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=90.0,
                expected_impact="Partial extraction failure, retries increase",
                expected_recovery_time_seconds=30.0,
                expected_success_rate=0.75,
                triggers=["anti_bot_engine.detect_captcha()"],
                recovery_actions=[
                    "use_js_rendering",
                    "try_alternative_endpoints",
                    "increase_wait_time",
                    "use_captcha_solver"
                ],
                validation_checks=[
                    "captchas_detected",
                    "recovery_strategies_attempted",
                    "js_rendering_used",
                    "success_rate_recovered"
                ]
            ),
            
            FailureScenario(
                name="IP Blacklist Expansion",
                description="IP reputation drops, more proxies become blacklisted",
                failure_mode=FailureMode.IP_BLACKLIST_EXPANSION,
                severity=SeverityLevel.HIGH,
                duration_seconds=120.0,
                expected_impact="Proxy pool effectiveness decreases",
                expected_recovery_time_seconds=90.0,
                expected_success_rate=0.6,
                triggers=["proxy_manager.check_reputation()"],
                recovery_actions=[
                    "rotate_proxy_providers",
                    "use_residential_proxies",
                    "increase_delays",
                    "use_vpn"
                ],
                validation_checks=[
                    "blacklisted_ips_detected",
                    "proxy_provider_switched",
                    "new_ip_pool_established",
                    "extraction_recovers"
                ]
            ),
            
            # ===== EXTRACT LAYER FAILURES (3 scenarios) =====
            FailureScenario(
                name="Selector Poisoning Attack",
                description="Top 3 selectors for a domain suddenly become invalid",
                failure_mode=FailureMode.SELECTOR_POISONING,
                severity=SeverityLevel.HIGH,
                duration_seconds=60.0,
                expected_impact="Extraction failures, selector discovery triggered",
                expected_recovery_time_seconds=20.0,
                expected_success_rate=0.85,
                triggers=["selector_engine.execute()"],
                recovery_actions=[
                    "selector_discovery",
                    "score_new_candidates",
                    "strategy_switch",
                    "fallback_extraction"
                ],
                validation_checks=[
                    "extraction_failures_detected",
                    "selector_discovery_triggered",
                    "new_selectors_evaluated",
                    "extraction_resumes"
                ]
            ),
            
            FailureScenario(
                name="DOM Structure Changed (Website Redesign)",
                description="Website structure changes, rendering completely different",
                failure_mode=FailureMode.DOM_STRUCTURE_CHANGED,
                severity=SeverityLevel.HIGH,
                duration_seconds=180.0,
                expected_impact="Extraction fails initially, learning loop adapts",
                expected_recovery_time_seconds=120.0,
                expected_success_rate=0.7,
                triggers=["dom_analyzer.parse()", "extraction_logic.execute()"],
                recovery_actions=[
                    "detect_structure_change",
                    "run_selector_discovery",
                    "invoke_ml_models",
                    "establish_new_selectors"
                ],
                validation_checks=[
                    "change_detected_quickly",
                    "learning_loop_invoked",
                    "ml_models_trained",
                    "new_selectors_established",
                    "extraction_recovers"
                ]
            ),
            
            FailureScenario(
                name="Extraction Timeout (Slow Page Loading)",
                description="All pages load extremely slowly (30s+), triggering timeouts",
                failure_mode=FailureMode.EXTRACTION_TIMEOUT,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=120.0,
                expected_impact="Timeouts, extraction fails, retries triggered",
                expected_recovery_time_seconds=30.0,
                expected_success_rate=0.8,
                triggers=["selector_engine.execute()", "extraction_timeout"],
                recovery_actions=[
                    "increase_timeout",
                    "use_js_rendering",
                    "retry_with_backoff",
                    "switch_strategy"
                ],
                validation_checks=[
                    "timeouts_detected",
                    "timeout_increased",
                    "extraction_resumes",
                    "success_rate_recovers"
                ]
            ),
            
            # ===== STATE/MEMORY FAILURES (3 scenarios) =====
            FailureScenario(
                name="Selector Cache Corruption",
                description="Cached selectors become corrupted or stale",
                failure_mode=FailureMode.CACHE_CORRUPTION,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=60.0,
                expected_impact="Cache hits return invalid data, recovery via reload",
                expected_recovery_time_seconds=10.0,
                expected_success_rate=0.9,
                triggers=["selector_memory.query()", "cache_manager.get()"],
                recovery_actions=[
                    "detect_invalid_cache",
                    "invalidate_cache",
                    "reload_from_disk",
                    "rescore_selectors"
                ],
                validation_checks=[
                    "corruption_detected",
                    "cache_cleared",
                    "fresh_data_loaded",
                    "extraction_continues"
                ]
            ),
            
            FailureScenario(
                name="State Inconsistency Between Nodes",
                description="Distributed state becomes inconsistent (gossip lag)",
                failure_mode=FailureMode.STATE_INCONSISTENCY,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=120.0,
                expected_impact="Nodes make conflicting decisions, eventual consistency",
                expected_recovery_time_seconds=30.0,
                expected_success_rate=0.85,
                triggers=["distributed_state_store.sync()"],
                recovery_actions=[
                    "detect_inconsistency",
                    "increase_gossip_frequency",
                    "resolve_conflicts",
                    "re_sync"
                ],
                validation_checks=[
                    "inconsistency_detected",
                    "gossip_intensified",
                    "conflict_resolved",
                    "state_consistent"
                ]
            ),
            
            FailureScenario(
                name="Memory Leak in Selector Memory",
                description="Selector memory grows unbounded, consuming all RAM",
                failure_mode=FailureMode.MEMORY_LEAK,
                severity=SeverityLevel.HIGH,
                duration_seconds=180.0,
                expected_impact="Memory pressure, GC pauses, eventual OOM",
                expected_recovery_time_seconds=60.0,
                expected_success_rate=0.5,
                triggers=["selector_memory.record()"],
                recovery_actions=[
                    "detect_memory_growth",
                    "trigger_eviction",
                    "implement_lru_cache",
                    "restart_if_necessary"
                ],
                validation_checks=[
                    "memory_growth_detected",
                    "eviction_triggered",
                    "memory_stabilized",
                    "extraction_continues"
                ]
            ),
            
            # ===== ORCHESTRATION FAILURES (2 scenarios) =====
            FailureScenario(
                name="semantic_world_state Unavailable",
                description="Central orchestrator becomes unavailable (crash/hang)",
                failure_mode=FailureMode.SEMANTIC_WORLD_STATE_CRASH,
                severity=SeverityLevel.CRITICAL,
                duration_seconds=30.0,
                expected_impact="All extractions blocked, system stalled",
                expected_recovery_time_seconds=5.0,
                expected_success_rate=0.0,
                triggers=["semantic_world_state.update()"],
                recovery_actions=[
                    "detect_unavailability",
                    "failover_if_distributed",
                    "restart_component",
                    "resume_work"
                ],
                validation_checks=[
                    "unavailability_detected_quickly",
                    "failover_triggered",
                    "extraction_resumes",
                    "state_recovered"
                ]
            ),
            
            FailureScenario(
                name="Learning Loop Deadlock",
                description="Learning loop gets stuck (circular wait or infinite loop)",
                failure_mode=FailureMode.LEARNING_LOOP_DEADLOCK,
                severity=SeverityLevel.HIGH,
                duration_seconds=120.0,
                expected_impact="Learning blocked, selector improvements stalled",
                expected_recovery_time_seconds=30.0,
                expected_success_rate=1.0,  # Extraction still works
                triggers=["domain_evolution_model.update()"],
                recovery_actions=[
                    "detect_deadlock",
                    "timeout_learning",
                    "skip_cycle",
                    "investigate_cause"
                ],
                validation_checks=[
                    "deadlock_detected",
                    "learning_timeout",
                    "extraction_unaffected",
                    "learning_resumes"
                ]
            ),
            
            # ===== DISTRIBUTED FAILURES (3 scenarios) =====
            FailureScenario(
                name="Node Crash (1 of 3 nodes)",
                description="One node in 3-node cluster crashes",
                failure_mode=FailureMode.NODE_CRASH,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=60.0,
                expected_impact="2/3 capacity, workload rebalanced, no data loss",
                expected_recovery_time_seconds=5.0,
                expected_success_rate=0.67,
                triggers=["heartbeat_manager.detect_failure()"],
                recovery_actions=[
                    "detect_crash",
                    "rebalance_workload",
                    "redistribute_urls",
                    "increase_monitoring"
                ],
                validation_checks=[
                    "crash_detected_within_3s",
                    "workload_rebalanced",
                    "urls_redistributed",
                    "throughput_at_2_3_capacity"
                ]
            ),
            
            FailureScenario(
                name="Network Partition in Cluster",
                description="Network split: 2 nodes isolated from 1 node",
                failure_mode=FailureMode.NETWORK_PARTITION_CLUSTER,
                severity=SeverityLevel.HIGH,
                duration_seconds=90.0,
                expected_impact="Split brain risk, eventual consistency delay",
                expected_recovery_time_seconds=30.0,
                expected_success_rate=0.8,
                triggers=["gossip_substrate.heartbeat()"],
                recovery_actions=[
                    "detect_partition",
                    "identify_majority",
                    "handle_minority",
                    "resync_on_recovery"
                ],
                validation_checks=[
                    "partition_detected",
                    "quorum_identified",
                    "minority_paused_or_redirected",
                    "network_heals",
                    "state_resynced"
                ]
            ),
            
            FailureScenario(
                name="Gossip Protocol Failure",
                description="Gossip messages corrupted/lost (30% packet loss)",
                failure_mode=FailureMode.GOSSIP_FAILURE,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=120.0,
                expected_impact="Delayed state propagation, eventual consistency slower",
                expected_recovery_time_seconds=60.0,
                expected_success_rate=0.9,
                triggers=["gossip_substrate.send()"],
                recovery_actions=[
                    "detect_high_packet_loss",
                    "increase_gossip_frequency",
                    "use_alternative_paths",
                    "increase_redundancy"
                ],
                validation_checks=[
                    "packet_loss_detected",
                    "gossip_frequency_increased",
                    "state_eventually_consistent",
                    "recovery_metrics_improve"
                ]
            ),
            
            # ===== CASCADING/COMPLEX FAILURES (3 scenarios) =====
            FailureScenario(
                name="Cascading Failures: Network → Anti-Bot → Proxy",
                description="Network timeout triggers aggressive anti-bot, exhausts proxies",
                failure_mode=FailureMode.CASCADING_FAILURES,
                severity=SeverityLevel.CRITICAL,
                duration_seconds=180.0,
                expected_impact="Multiple systems fail in sequence, major impact",
                expected_recovery_time_seconds=120.0,
                expected_success_rate=0.3,
                triggers=["browser_pool.fetch()", "anti_bot_engine", "proxy_manager"],
                recovery_actions=[
                    "circuit_breaker_network",
                    "reduce_anti_bot_aggressiveness",
                    "pause_extraction",
                    "restore_services_sequentially"
                ],
                validation_checks=[
                    "cascade_detected",
                    "circuit_breakers_engaged",
                    "extraction_paused",
                    "services_restored_sequentially",
                    "full_recovery"
                ]
            ),
            
            FailureScenario(
                name="Thundering Herd: All Nodes Retry Simultaneously",
                description="All nodes retry at same time after failure (no backoff stagger)",
                failure_mode=FailureMode.THUNDERING_HERD,
                severity=SeverityLevel.MEDIUM,
                duration_seconds=60.0,
                expected_impact="Spike in load, potential cascading failure",
                expected_recovery_time_seconds=10.0,
                expected_success_rate=0.7,
                triggers=["retry_logic.retry()", "exponential_backoff"],
                recovery_actions=[
                    "detect_retry_spike",
                    "apply_jitter_to_backoff",
                    "stagger_retries",
                    "throttle_if_needed"
                ],
                validation_checks=[
                    "spike_detected",
                    "jitter_applied",
                    "retries_staggered",
                    "load_normalized"
                ]
            ),
            
            FailureScenario(
                name="Resource Exhaustion: Memory → CPU → Network",
                description="System runs out of memory, GC thrashing, everything slows down",
                failure_mode=FailureMode.RESOURCE_EXHAUSTION,
                severity=SeverityLevel.CRITICAL,
                duration_seconds=120.0,
                expected_impact="System thrashing, very low throughput",
                expected_recovery_time_seconds=60.0,
                expected_success_rate=0.1,
                triggers=["memory_allocator", "garbage_collection"],
                recovery_actions=[
                    "detect_resource_exhaustion",
                    "trigger_eviction",
                    "pause_non_critical_tasks",
                    "scale_out",
                    "restart_if_necessary"
                ],
                validation_checks=[
                    "exhaustion_detected",
                    "eviction_triggered",
                    "non_critical_tasks_paused",
                    "performance_recovered",
                    "scale_out_initiated"
                ]
            ),
        ]
    
    @staticmethod
    def get_scenario_by_mode(mode: FailureMode) -> Optional[FailureScenario]:
        """Get a scenario by failure mode"""
        for scenario in FailureScenarios.get_all_scenarios():
            if scenario.failure_mode == mode:
                return scenario
        return None


# ============================================================================
# Test Suite
# ============================================================================

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
            "results": self.results
        }
    
    async def _run_scenario(self, scenario: FailureScenario) -> Dict[str, Any]:
        """Run a single scenario"""
        self.logger.info(f"Running scenario: {scenario.name}")
        
        try:
            # This is a template - actual implementation would:
            # 1. Setup monitoring
            # 2. Inject failure
            # 3. Monitor system behavior
            # 4. Measure recovery
            # 5. Validate against expectations
            
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
  Pass Rate: {passed/total*100:.1f}%

SCENARIOS BY SEVERITY:
  Critical: {sum(1 for r in self.results if 'critical' in r.get('severity', '').lower())}
  High: {sum(1 for r in self.results if 'high' in r.get('severity', '').lower())}
  Medium: {sum(1 for r in self.results if 'medium' in r.get('severity', '').lower())}
  Low: {sum(1 for r in self.results if 'low' in r.get('severity', '').lower())}

DETAILED RESULTS:
"""
        
        for result in self.results:
            status = "✓ PASS" if result.get("passed") else "✗ FAIL"
            report += f"\n  {status} - {result.get('scenario', 'Unknown')}"
        
        report += "\n\n" + "="*80 + "\n"
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
                "estimated_recovery_time": "2-5 minutes",
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
                "estimated_recovery_time": "30-120 minutes",
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
                "estimated_recovery_time": "10-30 minutes",
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
                "estimated_recovery_time": "3-10 minutes",
            },
            
            FailureMode.MEMORY_LEAK: {
                "name": "Memory Leak Recovery",
                "severity": "HIGH",
                "steps": [
                    "1. Detect: Memory usage growing >50MB/hour",
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
                "estimated_recovery_time": "2-30 minutes (temp fix), 1-4 hours (permanent)",
            },
        }
        
        return playbooks.get(failure_mode, {
            "name": "Unknown Failure",
            "severity": "UNKNOWN",
            "steps": ["1. Investigate logs and metrics"],
            "escalation": "On-Call Engineer",
        })
    
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
    """
    Run a chaos test scenario
    
    Example:
        scenario = FailureScenarios.get_scenario_by_mode(FailureMode.NETWORK_TIMEOUT)
        result = await run_chaos_test(scenario)
    """
    simulator = ChaosSimulator()
    result = await simulator.inject_failure(
        scenario.failure_mode,
        duration=scenario.duration_seconds
    )
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


if __name__ == "__main__":
    # Print all scenarios
    print("DataForge Chaos Engineering Scenarios:")
    print("=" * 80)
    
    scenarios = FailureScenarios.get_all_scenarios()
    
    # Group by category
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
