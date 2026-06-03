"""
Research Shell Boundary — single source of truth for which modules are
classified as experimental / research-only.

This module exists for ONE reason: to give the codebase a deterministic,
machine-checkable answer to the question "is module X part of the product
kernel or part of the research shell?".

Why this matters
----------------
The repo's deep-research-report and PROJECT_STATUS.md both call out a
central architectural problem: the product kernel and a large research
shell (semantic world state, topology, federation, gossip, motif, energy,
instability, strategy evolution, chaos, replay, etc.) share the same
import graph. This makes it impossible to know, without tracing every
import by hand, which capabilities are production-validated and which are
experimental.

By listing those modules here once, we make the boundary:

1. **Auditable.** One file lists every experimental module. A code review
   can verify nothing in the product kernel is silently re-classified.
2. **Gateable.** `is_research_module()` and the `ENABLE_EXPERIMENTAL_ROUTES`
   flag in config combine to form a hard import-time gate.
3. **Stable.** Adding a new research module requires editing this list,
   which is exactly the moment a human should be deciding "is this part
   of the product or is this a research experiment?".

Classification rule
-------------------
A module is "research" if it implements a capability explicitly called out
in the deep-research-report's "Move out or quarantine" column, OR if it
belongs to one of the named research families (semantic, topology,
federation, gossip, motif, energy, instability, strategy evolution,
chaos, replay, acquisition, intent, abstraction, manifold, field_laws,
degradation, trend, vector_clock, invariant_firewall, insight_engine,
recovery_strategies/failure_injector, snapshot_desync).

A module is "product kernel" if it is required to fulfil the validated
product contract: job lifecycle APIs, HTTP/Playwright fetching,
deterministic extraction, cleaning, persistence, exports, metrics,
diagnostics, auth, RBAC, rate limiting, SSRF controls.

Anything ambiguous defaults to "research" — better to quarantine
something useful than to silently leak an experimental dependency into
the product kernel.
"""

from __future__ import annotations

from typing import FrozenSet

# ─── Research module registry ──────────────────────────────────────────────
#
# Module names are bare basenames (no package prefix). They are matched
# against the import target of `from app import X` and `from app.X import
# Y` patterns, and against top-level module filenames in `app/`.
#
# To move a module OUT of the research shell (e.g. once it is
# production-validated), remove it from this set AND from any
# lazy-load gate that references it. The change must be intentional
# and code-reviewed.

RESEARCH_MODULES: FrozenSet[str] = frozenset(
    {
        # ── Semantic world state and friends ────────────────────────────
        "semantic_world_state",  # package (submodules: core, events, locks, etc.)
        "semantic_os",
        "semantic_ir",
        "semantic_persistence",
        "semantic_mapper",
        "semantic_pipeline",
        "semantic_events",
        "semantic_inference_engine",
        "semantic_segmentation",
        "semantic_boundary_engine",
        "semantic_allocation_engine",
        # ── Topology / manifold / motif / energy / instability ──────────
        "topology_state",
        "topology_state_types",
        "topology_api",
        "topology_view",
        "topology_dynamics",
        "topology_clustering",
        "topology_persistence",
        "topology_metrics",
        "topology_gc",
        "topological_query",
        "manifold_state",
        "motif_state",
        "motif_feedback",
        "energy_state",
        "energy_api",
        "instability_state",
        "instability_api",
        # ── Federation / gossip / heartbeat ─────────────────────────────
        "federation_manager",
        "gossip_substrate",
        "heartbeat_manager",
        # ── Field laws / invariant firewall / abstraction / action ─────
        "field_laws",
        "field_validator",
        "invariant_firewall",
        "abstraction_state",
        "action_state",
        # ── Intent / acquisition ───────────────────────────────────────
        "intent_parser",
        "intent_state",
        "acquisition_mode",
        "acquisition_state",
        "acquisition_telemetry",
        # ── Chaos / failure injection / replay ─────────────────────────
        "chaos_simulator",
        "chaos_scenarios",
        "chaos_metrics",
        "failure_injector",
        "replay_buffer",
        "snapshot_desync_detector",
        # ── Strategy evolution / self-tuning / domain evolution ────────
        "strategy_evolution",
        "self_tuning_extraction",
        "domain_evolution_model",
        "selector_ml_optimizer",
        "selector_decay_predictor",
        "degradation_predictor",
        "trend_analyzer",
        "vector_clock",
        "insight_engine",
    }
)


# Second slice of the registry — modules whose classification was
# ambiguous on first pass and which we have now conservatively placed
# in the research shell. Promotion to product-kernel status requires
# (a) a dedicated audit, (b) removal from this set, and (c) updating
# the lazy-load gates that currently guard their import.

_EXTRA_RESEARCH_MODULES: FrozenSet[str] = frozenset(
    {
        # ── Recovery strategies (the experimental recovery framework) ──
        # `recovery_handlers` is part of the product kernel (it is
        # registered via experimental_startup), but `recovery_strategies`
        # and `scraper_recovery_integration` are the research variants.
        "recovery_strategies",
        "scraper_recovery_integration",
        # ── History / persistence state / event journal ────────────────
        # `event_journal` is used by both production diagnostics and the
        # research replay path. Classify as research for now.
        "event_journal",
        "history_state",
        "persistence_state",
        "telemetry_state",
        "transition_state",
        "crawl_state",
        # ── Resource governance / runtime budget ────────────────────────
        # Both are used by kernel fetch/extract budgets and research
        # cognitive-task budgets. The full governor is not part of the
        # validated product contract.
        "resource_governor",
        "runtime_budget",
        "transactional_priority_queue",
        "transaction_context",
        # ── Domain health / domain runtime policy ──────────────────────
        # Production routing uses `crawl_policy`. The runtime-policy and
        # health-alerts modules are part of the research acquisition loop.
        "domain_health_alerts",
        "domain_runtime_policy",
        # ── Graph update scheduler (event cascade) ─────────────────────
        "graph_update_scheduler",
        # ── Event dispatcher (used by research and kernel; classify as
        # research until a clean split exists) ─────────────────────────
        "event_dispatcher",
        # ── Policy engine (research variant) ───────────────────────────
        "policy_engine",
        # ── Patch status / patch health ────────────────────────────────
        "patch_status",
        # ── Visualization (used only by experimental dashboard) ───────
        "visualization",
    }
)

RESEARCH_MODULES = RESEARCH_MODULES | _EXTRA_RESEARCH_MODULES


def is_research_module(name: str | None) -> bool:
    """Return True if `name` is a research/experimental module.

    `name` may be a bare module basename (e.g. `"semantic_world_state"`)
    or a dotted import path with any number of sub-modules
    (e.g. `"app.semantic_world_state.core"` or
    `"backend.app.semantic_os.events"`). The function strips any
    leading `backend.` / `app.` / `src.` segments and tests the first
    remaining segment against the registry.

    This is intentionally the same algorithm as `is_research_path` so
    callers don't have to remember which one to use.
    """
    return is_research_path(name)


def is_research_path(qualified_name: str | None) -> bool:
    """Return True if a fully-qualified module name is part of the research shell.

    Examples:
        >>> is_research_path("app.semantic_world_state")
        True
        >>> is_research_path("app.semantic_world_state.core")
        True
        >>> is_research_path("app.scraper")
        False
        >>> is_research_path("backend.app.semantic_os")
        True
    """
    if not qualified_name:
        return False
    parts = qualified_name.split(".")
    # Strip leading "backend" / "app" / "src" segments so we land on the basename.
    while parts and parts[0] in {"backend", "app", "src"}:
        parts.pop(0)
    if not parts:
        return False
    return parts[0] in RESEARCH_MODULES


# ─── Family classification for diagnostics ─────────────────────────────────

_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "semantic",
        ("semantic_world_state",)
        + tuple(
            f"semantic_{s}"
            for s in (
                "os",
                "ir",
                "persistence",
                "mapper",
                "pipeline",
                "events",
                "inference_engine",
                "segmentation",
                "boundary_engine",
                "allocation_engine",
            )
        ),
    ),
    (
        "topology_manifold",
        (
            "topology_state",
            "topology_state_types",
            "topology_api",
            "topology_view",
            "topology_dynamics",
            "topology_clustering",
            "topology_persistence",
            "topology_metrics",
            "topology_gc",
            "topological_query",
            "manifold_state",
            "motif_state",
            "motif_feedback",
            "energy_state",
            "energy_api",
            "instability_state",
            "instability_api",
        ),
    ),
    ("federation_gossip", ("federation_manager", "gossip_substrate", "heartbeat_manager")),
    (
        "field_abstraction",
        (
            "field_laws",
            "field_validator",
            "invariant_firewall",
            "abstraction_state",
            "action_state",
        ),
    ),
    (
        "intent_acquisition",
        (
            "intent_parser",
            "intent_state",
            "acquisition_mode",
            "acquisition_state",
            "acquisition_telemetry",
        ),
    ),
    (
        "chaos_replay",
        (
            "chaos_simulator",
            "chaos_scenarios",
            "chaos_metrics",
            "failure_injector",
            "replay_buffer",
            "snapshot_desync_detector",
        ),
    ),
    (
        "strategy_evolution",
        (
            "strategy_evolution",
            "self_tuning_extraction",
            "domain_evolution_model",
            "selector_ml_optimizer",
            "selector_decay_predictor",
            "degradation_predictor",
            "trend_analyzer",
            "vector_clock",
            "insight_engine",
        ),
    ),
    (
        "recovery_history",
        (
            "recovery_strategies",
            "scraper_recovery_integration",
            "event_journal",
            "history_state",
            "persistence_state",
            "telemetry_state",
            "transition_state",
            "crawl_state",
        ),
    ),
    (
        "governance_budget",
        (
            "resource_governor",
            "runtime_budget",
            "transactional_priority_queue",
            "transaction_context",
            "event_dispatcher",
            "policy_engine",
            "patch_status",
            "graph_update_scheduler",
        ),
    ),
    ("domain_runtime", ("domain_health_alerts", "domain_runtime_policy")),
    ("misc", ("visualization",)),
)


def research_summary() -> dict[str, list[str]]:
    """Return a structured summary of the registry for diagnostics endpoints.

    The summary is grouped by family so the report-style audit view can
    show a per-family count without forcing callers to re-classify.
    """
    families: dict[str, list[str]] = {family: [] for family, _ in _FAMILY_RULES}
    family_lookup: dict[str, str] = {name: family for family, members in _FAMILY_RULES for name in members}
    for name in sorted(RESEARCH_MODULES):
        family = family_lookup.get(name, "misc")
        families[family].append(name)
    families["total_count"] = [str(len(RESEARCH_MODULES))]
    return families


__all__ = [
    "RESEARCH_MODULES",
    "is_research_module",
    "is_research_path",
    "research_summary",
]
