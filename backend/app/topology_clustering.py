"""Topology clustering — community detection, sharding, and law induction.

These functions operate on a TopologyState instance for all community-level
management and topological pattern discovery.

Extracted from topology_state.py for modularity (see REFACTOR_PLAN.md).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.topology_state import TopologyState


# ─── Community Detection ────────────────────────────────────────────────


def detect_communities(state: "TopologyState") -> None:  # noqa: C901, PLR0912
    """Flood-fill communities from cohesion + field regions."""
    graph: dict[str, set[str]] = {}
    cohesion = state._get_struct("neighborhood_cohesion")
    for (ra, rb), val in cohesion.items():
        if val > 0.5:
            graph.setdefault(ra, set()).add(rb)
            graph.setdefault(rb, set()).add(ra)
    for r in state._get_regions():
        for i in range(len(r.competing_roles)):
            for j in range(i + 1, len(r.competing_roles)):
                ra, rb = r.competing_roles[i], r.competing_roles[j]
                graph.setdefault(ra, set()).add(rb)
                graph.setdefault(rb, set()).add(ra)
    if not graph:
        from app.field_laws import ROLE_EXCLUSIVITY

        for ra, rb in ROLE_EXCLUSIVITY:
            graph.setdefault(ra, set()).add(rb)
            graph.setdefault(rb, set()).add(ra)
    seen = set()
    communities = []
    for node in graph:
        if node in seen:
            continue
        component = set()
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            component.add(cur)
            for neighbor in graph.get(cur, set()):
                if neighbor not in seen:
                    stack.append(neighbor)  # noqa: PERF401
        if component:
            communities.append(component)
    state._set_struct("communities", communities)


def shard_topology_regions(state: "TopologyState") -> dict[str, list[str]]:
    """Assign every region to a shard based on community membership (Phase 53).

    Returns a dict mapping shard_id -> list of region_ids.
    """
    communities = state._get_struct("communities")
    role_to_shard = {}
    for idx, community in enumerate(communities):
        shard_id = f"shard_{idx}"
        for role in community:
            role_to_shard[role] = shard_id

    shard_assignment: dict[str, list[str]] = {}
    for r in state._get_regions():
        primary_role = r.competing_roles[0] if r.competing_roles else "_unidentified"
        shard_id = role_to_shard.get(primary_role, "shard_default")
        shard_assignment.setdefault(shard_id, []).append(r.region_id)

    return shard_assignment


# ─── Schema Patterns ────────────────────────────────────────────────────


def update_schema_patterns(state: "TopologyState", exclusion_key: tuple, exclusion_val: float) -> None:
    """Update schema patterns with exponential moving average."""
    struct = state._get_struct("schema_patterns")
    cur = struct.get(exclusion_key, 0.0)
    struct[exclusion_key] = cur * 0.95 + exclusion_val * 0.05
    state._set_struct("schema_patterns", struct)


# ─── Topological Laws ───────────────────────────────────────────────────


def decay_topological_laws(state: "TopologyState") -> None:
    """Apply exponential decay to all topological laws."""
    from app.topology_state_types import _clamp_signed

    struct = state._get_struct("topological_laws")
    for key in list(struct.keys()):
        struct[key] = _clamp_signed(struct[key] * 0.95)
        if abs(struct[key]) <= 0.005:
            del struct[key]
    state._set_struct("topological_laws", struct)


def set_topological_law(state: "TopologyState", pair: tuple, value: float) -> None:
    """Set a topological law for a role pair."""
    from app.topology_state_types import _clamp_signed

    laws = state._get_struct("topological_laws")
    laws[tuple(sorted(pair))] = _clamp_signed(value)
    state._set_struct("topological_laws", laws)
    state._record("set_topological_law", {"pair": pair, "value": value})


def add_impossible_neighborhood(state: "TopologyState", item: set[str]) -> None:
    """Add an impossible neighborhood set."""
    struct = state._get_struct("impossible_neighborhoods")
    struct.append(set(item))
    state._set_struct("impossible_neighborhoods", struct)


def clear_impossible_neighborhoods(state: "TopologyState") -> None:
    """Clear all impossible neighborhoods."""
    struct = state._get_struct("impossible_neighborhoods")
    struct.clear()
    state._set_struct("impossible_neighborhoods", struct)


# ─── Autonomous Pruning & Law Induction ─────────────────────────────────


def self_prune_regions(
    state: "TopologyState",
    instability_threshold: float = 0.9,
    community_required: bool = True,  # noqa: FBT001, FBT002
) -> int:
    """Autonomous topology pruning (Phase 62).

    Removes regions that:
    1. Have very high instability (> threshold)
    2. Are NOT part of any detected community (isolated noise)
    """
    regs = state._get_regions()
    if not regs:
        return 0

    before = len(regs)
    in_community = set().union(*state.global_communities)

    new_regs = []
    for r in regs:
        is_noise = r.instability > instability_threshold
        has_community = any(role in in_community for role in r.competing_roles)

        if is_noise and community_required and not has_community:
            state._record("prune_dead_zone", {"region_id": r.region_id, "instability": r.instability})
            state._structural_change = True
            continue

        new_regs.append(r)

    state._set_regions(new_regs)
    return before - len(new_regs)


def induce_topological_laws(
    state: "TopologyState",
    min_success_rate: float = 0.8,
    min_attempts: int = 10,
) -> None:
    """Autonomous law discovery (Phase 62).

    Promotes frequently successful structural patterns into formal laws.
    """
    for pair, success in state._cohesion_merge_success.items():
        attempts = state._cohesion_merge_attempts.get(pair, 0)
        if attempts >= min_attempts:
            rate = success / attempts
            if rate >= min_success_rate:
                current = state.topological_laws.get(pair, 0.0)
                set_topological_law(state, pair, max(current, 0.5 + (rate - 0.5) * 0.5))
                state._record("induce_law", {"pair": pair, "type": "affinity", "rate": rate})

    for pair, success in state._cohesion_split_success.items():
        attempts = state._cohesion_split_attempts.get(pair, 0)
        if attempts >= min_attempts:
            rate = success / attempts
            if rate >= min_success_rate:
                current = state.topological_laws.get(pair, 0.0)
                set_topological_law(state, pair, min(current, -0.5 * rate))
                state._record("induce_law", {"pair": pair, "type": "repulsion", "rate": rate})
