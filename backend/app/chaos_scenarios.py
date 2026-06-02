"""Chaos scenarios — failure definitions and scenario collection.

Contains the failure mode taxonomy, severity levels, scenario data models,
and the predefined collection of chaos test scenarios.

Extracted from chaos_simulator.py for modularity (see REFACTOR_PLAN.md).
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


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

    # Memory / State
    CACHE_CORRUPTION = "cache_corruption"
    STATE_INCONSISTENCY = "state_inconsistency"
    MEMORY_LEAK = "memory_leak"
    PERSISTENCE_FAILURE = "persistence_failure"

    # Intelligence / Orchestration
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

    LOW = "low"  # Recoverable, <1% impact
    MEDIUM = "medium"  # Recoverable, 1 - 10% impact
    HIGH = "high"  # Recoverable with effort, 10 - 50% impact
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
                validation_checks=["extraction_retried", "backoff_applied", "system_recovers_after_timeout"],
            ),
            FailureScenario(
                name="Network Partition (Total)",
                description="Complete network isolation - no packets sent / received",
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
                    "backlog_processed",
                ],
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
                    "extraction_continues",
                ],
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
                    "recovery_automatic",
                ],
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
                validation_checks=["ssl_errors_detected", "retry_triggered", "ops_alerted", "recovery_attempted"],
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
                    "blacklist_domain",
                ],
                validation_checks=[
                    "detection_rate_climbing",
                    "recovery_strategies_applied",
                    "domain_health_recovered_or_blacklisted",
                    "no_cascading_failure",
                ],
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
                    "use_captcha_solver",
                ],
                validation_checks=[
                    "captchas_detected",
                    "recovery_strategies_attempted",
                    "js_rendering_used",
                    "success_rate_recovered",
                ],
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
                recovery_actions=["rotate_proxy_providers", "use_residential_proxies", "increase_delays", "use_vpn"],
                validation_checks=[
                    "blacklisted_ips_detected",
                    "proxy_provider_switched",
                    "new_ip_pool_established",
                    "extraction_recovers",
                ],
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
                    "fallback_extraction",
                ],
                validation_checks=[
                    "extraction_failures_detected",
                    "selector_discovery_triggered",
                    "new_selectors_evaluated",
                    "extraction_resumes",
                ],
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
                    "establish_new_selectors",
                ],
                validation_checks=[
                    "change_detected_quickly",
                    "learning_loop_invoked",
                    "ml_models_trained",
                    "new_selectors_established",
                    "extraction_recovers",
                ],
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
                recovery_actions=["increase_timeout", "use_js_rendering", "retry_with_backoff", "switch_strategy"],
                validation_checks=[
                    "timeouts_detected",
                    "timeout_increased",
                    "extraction_resumes",
                    "success_rate_recovers",
                ],
            ),
            # ===== STATE / MEMORY FAILURES (3 scenarios) =====
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
                recovery_actions=["detect_invalid_cache", "invalidate_cache", "reload_from_disk", "rescore_selectors"],
                validation_checks=["corruption_detected", "cache_cleared", "fresh_data_loaded", "extraction_continues"],
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
                recovery_actions=["detect_inconsistency", "increase_gossip_frequency", "resolve_conflicts", "re_sync"],
                validation_checks=[
                    "inconsistency_detected",
                    "gossip_intensified",
                    "conflict_resolved",
                    "state_consistent",
                ],
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
                    "restart_if_necessary",
                ],
                validation_checks=[
                    "memory_growth_detected",
                    "eviction_triggered",
                    "memory_stabilized",
                    "extraction_continues",
                ],
            ),
            # ===== ORCHESTRATION FAILURES (2 scenarios) =====
            FailureScenario(
                name="Semantic World State Unavailable",
                description="Central orchestrator becomes unavailable (crash / hang)",
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
                    "resume_work",
                ],
                validation_checks=[
                    "unavailability_detected_quickly",
                    "failover_triggered",
                    "extraction_resumes",
                    "state_recovered",
                ],
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
                recovery_actions=["detect_deadlock", "timeout_learning", "skip_cycle", "investigate_cause"],
                validation_checks=[
                    "deadlock_detected",
                    "learning_timeout",
                    "extraction_unaffected",
                    "learning_resumes",
                ],
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
                recovery_actions=["detect_crash", "rebalance_workload", "redistribute_urls", "increase_monitoring"],
                validation_checks=[
                    "crash_detected_within_3s",
                    "workload_rebalanced",
                    "urls_redistributed",
                    "throughput_at_2_3_capacity",
                ],
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
                recovery_actions=["detect_partition", "identify_majority", "handle_minority", "resync_on_recovery"],
                validation_checks=[
                    "partition_detected",
                    "quorum_identified",
                    "minority_paused_or_redirected",
                    "network_heals",
                    "state_resynced",
                ],
            ),
            FailureScenario(
                name="Gossip Protocol Failure",
                description="Gossip messages corrupted / lost (30% packet loss)",
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
                    "increase_redundancy",
                ],
                validation_checks=[
                    "packet_loss_detected",
                    "gossip_frequency_increased",
                    "state_eventually_consistent",
                    "recovery_metrics_improve",
                ],
            ),
            # ===== CASCADING / COMPLEX FAILURES (3 scenarios) =====
            FailureScenario(
                name="Cascading Failures: Network -> Anti-Bot -> Proxy",
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
                    "restore_services_sequentially",
                ],
                validation_checks=[
                    "cascade_detected",
                    "circuit_breakers_engaged",
                    "extraction_paused",
                    "services_restored_sequentially",
                    "full_recovery",
                ],
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
                    "throttle_if_needed",
                ],
                validation_checks=["spike_detected", "jitter_applied", "retries_staggered", "load_normalized"],
            ),
            FailureScenario(
                name="Resource Exhaustion: Memory -> CPU -> Network",
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
                    "restart_if_necessary",
                ],
                validation_checks=[
                    "exhaustion_detected",
                    "eviction_triggered",
                    "non_critical_tasks_paused",
                    "performance_recovered",
                    "scale_out_initiated",
                ],
            ),
        ]

    @staticmethod
    def get_scenario_by_mode(mode: FailureMode) -> Optional[FailureScenario]:
        """Get a scenario by failure mode"""
        for scenario in FailureScenarios.get_all_scenarios():
            if scenario.failure_mode == mode:
                return scenario
        return None
