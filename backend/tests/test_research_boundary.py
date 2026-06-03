"""
Unit tests for the research-shell boundary registry.

These tests pin down three contracts:

1. The registry exists and is non-empty.
2. `is_research_module` and `is_research_path` correctly classify
   well-known research modules and well-known product-kernel modules.
3. The family summary groups every registered module (no orphans).

The tests are intentionally tolerant of additions to the registry: if
someone adds a new research module, these tests do not need to change.
If someone removes a module from the registry, the spot-checks below
will fail — that is the desired signal.
"""

from __future__ import annotations

from app.research import (
    RESEARCH_MODULES,
    is_research_module,
    is_research_path,
    research_summary,
)

# ─── Spot-checks: well-known research modules ──────────────────────────────

RESEARCH_SPOT_CHECKS = (
    "semantic_world_state",
    "semantic_os",
    "topology_state",
    "topology_api",
    "manifold_state",
    "motif_state",
    "energy_state",
    "instability_state",
    "federation_manager",
    "gossip_substrate",
    "heartbeat_manager",
    "field_laws",
    "invariant_firewall",
    "abstraction_state",
    "action_state",
    "intent_parser",
    "acquisition_state",
    "chaos_simulator",
    "replay_buffer",
    "strategy_evolution",
    "self_tuning_extraction",
    "selector_ml_optimizer",
    "degradation_predictor",
    "vector_clock",
    "insight_engine",
)


# ─── Spot-checks: well-known product-kernel modules ────────────────────────

KERNEL_SPOT_CHECKS = (
    "scraper",
    "extraction_orchestrator",
    "config",
    "lifespan",
    "main",
    "middlewares",
    "models",
    "storage_interface",
    "postgres_repository",
    "worker_queue",
    "worker_queue_postgres",
    "url_safety",
    "rate_limiter",
    "rbac",
    "audit_logger",
    "metrics_collector",
    "globals",
    "lifespan",
)


def test_registry_is_non_empty():
    assert len(RESEARCH_MODULES) > 0
    # We expect at least 50 research modules — the deep-research-report
    # enumerates roughly that many.
    assert len(RESEARCH_MODULES) >= 50


def test_all_research_spot_checks_are_registered():
    for name in RESEARCH_SPOT_CHECKS:
        assert (
            name in RESEARCH_MODULES
        ), f"Expected {name!r} to be in the research registry. Either add it or update the spot-check."


def test_all_kernel_spot_checks_are_NOT_registered():
    for name in KERNEL_SPOT_CHECKS:
        assert name not in RESEARCH_MODULES, (
            f"{name!r} is a product-kernel module and must NOT be in the "
            f"research registry. Either the classification is wrong or the "
            f"module is being re-purposed — both are intentional decisions."
        )


def test_is_research_module_accepts_bare_names():
    assert is_research_module("semantic_world_state") is True
    assert is_research_module("topology_state") is True
    assert is_research_module("scraper") is False
    assert is_research_module("extraction_orchestrator") is False


def test_is_research_module_accepts_dotted_paths():
    assert is_research_module("app.semantic_world_state") is True
    assert is_research_module("app.semantic_world_state.core") is True
    assert is_research_module("backend.app.topology_state") is True
    assert is_research_module("app.scraper") is False


def test_is_research_module_handles_empty_and_junk_input():
    assert is_research_module("") is False
    assert is_research_module(None) is False


def test_is_research_path_strips_known_package_prefixes():
    assert is_research_path("app.semantic_os") is True
    assert is_research_path("backend.app.semantic_os") is True
    assert is_research_path("app.scraper") is False
    assert is_research_path("backend.app.scraper") is False


def test_is_research_path_handles_empty_input():
    assert is_research_path("") is False


def test_research_summary_groups_every_module():
    summary = research_summary()
    total_count = int(summary["total_count"][0])
    assert total_count == len(RESEARCH_MODULES)
    # Sum of all family lists must equal the total (no orphans, no duplicates).
    counted = sum(len(modules) for family, modules in summary.items() if family != "total_count")
    assert counted == total_count, (
        f"Family summary accounts for {counted} modules but registry has "
        f"{total_count}. Check that every module appears in _FAMILY_RULES."
    )


def test_research_summary_includes_all_expected_families():
    summary = research_summary()
    expected_families = {
        "semantic",
        "topology_manifold",
        "federation_gossip",
        "field_abstraction",
        "intent_acquisition",
        "chaos_replay",
        "strategy_evolution",
        "recovery_history",
        "governance_budget",
        "domain_runtime",
        "misc",
    }
    assert expected_families.issubset(summary.keys())


def test_research_summary_is_sorted_within_each_family():
    summary = research_summary()
    for family, modules in summary.items():
        if family == "total_count":
            continue
        assert modules == sorted(modules), f"Family {family!r} should be sorted alphabetically."


def test_registry_is_immutable():
    """`frozenset` should reject mutation; verify the type contract."""
    assert isinstance(RESEARCH_MODULES, frozenset)
