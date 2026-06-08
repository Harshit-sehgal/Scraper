"""Topology persistence — serialization, deserialization, merge, clear.

These functions operate on a TopologyState instance for all topology-level
serialization and lifecycle operations.

Extracted from topology_state.py for modularity (see REFACTOR_PLAN.md).
"""

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.topology_state import TopologyState
    # FieldConflictRegion is imported at function level to avoid redefinition warnings


# ─── Bulk Region Lifecycle ──────────────────────────────────────────────


def replace_all_regions(state: "TopologyState", new_regions: list) -> None:
    """Replace the entire regional manifold (Phase 50)."""
    state.set_regions(list(new_regions))
    if state._staging is not None:
        state._staging["structural_change"] = True
    state.record("replace_all_regions", {"count": len(new_regions)})


def trim_topology(state: "TopologyState", max_size: int, keep_from_end: int = 0) -> None:
    """Trim regions to a maximum size, optionally keeping from the end."""
    regs = state.get_regions()
    if len(regs) > max_size:
        regs = regs[-keep_from_end:] if keep_from_end > 0 else regs[-max_size:]
        state.set_regions(regs)
        if state._staging is not None:
            state._staging["structural_change"] = True


def filter_topology_regions(state: "TopologyState", predicate: Callable[..., bool]) -> None:
    """Filter regions using a predicate function."""
    regs = [r for r in state.get_regions() if predicate(r)]
    state.set_regions(regs)
    if state._staging is not None:
        state._staging["structural_change"] = True


def prune_topology(state: "TopologyState", min_instability: float = 0.02, min_energy: float = 0.5) -> int:
    """Prune regions below instability and energy thresholds."""
    regs = state.get_regions()
    before = len(regs)
    regs = [r for r in regs if r.instability > min_instability or r.local_energy > min_energy]
    state.set_regions(regs)
    if len(regs) != before and state._staging is not None:
        state._staging["structural_change"] = True
    return before - len(regs)


def garbage_collect_topology(state: "TopologyState", max_idle: int = 10) -> int:
    """Resource-aware pruning of dead semantic regions (Phase 9)."""
    regs = state.get_regions()
    before = len(regs)
    regs = [r for r in regs if r.idle_cycles < max_idle]
    state.set_regions(regs)
    if len(regs) != before and state._staging is not None:
        state._staging["structural_change"] = True
    return before - len(regs)


# ─── Serialization ──────────────────────────────────────────────────────


def topology_to_dict(state: "TopologyState") -> dict:
    """Serialize the full topology state to a dict."""
    from dataclasses import asdict

    return {
        "regions": [asdict(r) for r in state.get_regions()],
        "communities": [list(c) for c in state.global_communities],
        "schema_patterns": {str(k): v for k, v in state.schema_patterns.items()},
        "topological_laws": {str(k): v for k, v in state.topological_laws.items()},
        "neighborhood_cohesion": {str(k): v for k, v in state.neighborhood_cohesion.items()},
        "cohesion_merge_success": {str(k): v for k, v in state.get_cohesion_merge_success().items()},
        "cohesion_merge_attempts": {str(k): v for k, v in state.get_cohesion_merge_attempts().items()},
        "cohesion_split_success": {str(k): v for k, v in state.get_cohesion_split_success().items()},
        "cohesion_split_attempts": {str(k): v for k, v in state.get_cohesion_split_attempts().items()},
        "centrality": state.global_centrality,
        "anchors": [list(a) for a in state.anchors],
        "impossible_neighborhoods": [list(n) for n in state.impossible_neighborhoods],
        "restructuring_queue": [list(r) for r in state.restructuring_queue],
        "crystalline_atoms": list(state.get_struct("crystalline_atoms")),
        "meso_clusters": list(state.get_struct("meso_clusters")),
        "macro_continents": list(state.get_struct("macro_continents")),
        "topology_epoch": state.topology_epoch,
        "tombstones": list(state.tombstones),
    }


def topology_from_dict(state: "TopologyState", data: dict) -> None:
    """Deserialize topology state from a dict."""
    from app.core_types import FieldConflictRegion
    from app.topology_state_types import parse_topology_key

    state.clear()

    # Identity and Epoch (Phase 60)
    state.topology_epoch = data.get("topology_epoch", 1)
    state.tombstones = set(data.get("tombstones", []))

    # Regions
    regions = []
    for r_data in data.get("regions", []):
        r = FieldConflictRegion(
            competing_roles=r_data["competing_roles"],
            token=r_data["token"],
            instability=r_data["instability"],
            region_id=r_data.get("region_id"),
        )
        for k, v in r_data.items():
            if k not in ["competing_roles", "token", "instability", "region_id"]:
                setattr(r, k, v)
        regions.append(r)
    state.set_regions(regions)

    # Communities
    state.set_struct("communities", [set(c) for c in data.get("communities", [])])

    # Pipe-separated-key dicts or tuple keys
    for data_key, struct_key in [
        ("schema_patterns", "schema_patterns"),
        ("topological_laws", "topological_laws"),
        ("neighborhood_cohesion", "neighborhood_cohesion"),
        ("cohesion_merge_success", "merge_success"),
        ("cohesion_merge_attempts", "merge_attempts"),
        ("cohesion_split_success", "split_success"),
        ("cohesion_split_attempts", "split_attempts"),
    ]:
        target = {}
        for k, v in data.get(data_key, {}).items():
            if isinstance(k, str):
                if "|" in k:
                    parts = k.split("|")
                    if len(parts) == 2:
                        target[tuple(parts)] = v
                else:
                    try:
                        target[parse_topology_key(k)] = v
                    except ValueError:
                        target[tuple(k.split("|"))] = v
            else:
                target[tuple(k)] = v
        state.set_struct(struct_key, target)

    # Simple replacements
    state.set_struct("centrality", dict(data.get("centrality", {})))
    state.set_struct("impossible_neighborhoods", [set(n) for n in data.get("impossible_neighborhoods", [])])
    state.set_struct("restructuring_queue", {tuple(r) for r in data.get("restructuring_queue", [])})
    state.set_struct("anchors", {tuple(a) for a in data.get("anchors", []) if len(a) == 2})
    state.set_struct("crystalline_atoms", list(data.get("crystalline_atoms", [])))
    state.set_struct("meso_clusters", list(data.get("meso_clusters", [])))
    state.set_struct("macro_continents", list(data.get("macro_continents", [])))


# ─── Merge / Reconciliation ─────────────────────────────────────────────


def merge_topology(state: "TopologyState", other_data: dict, alpha: float = 0.5) -> None:
    """Merge remote topology state into local (Phase 32 / 60)."""
    from app.core_types import FieldConflictRegion
    from app.topology_state_types import parse_topology_key

    remote_epoch = other_data.get("topology_epoch", 1)
    remote_tombstones = set(other_data.get("tombstones", []))

    # Phase 60: Causal Reconciliation Heuristic
    state.tombstones.update(remote_tombstones)

    state.topology_epoch = max(state.topology_epoch, remote_epoch)

    if remote_epoch >= state.topology_epoch:
        regs = state.get_regions()
        new_regs = [r for r in regs if r.region_id not in remote_tombstones]
        if len(new_regs) < len(regs):
            state.set_regions(new_regs)
            state.structural_change = True

    remote_regions = other_data.get("regions", [])
    local_ids = {r.region_id: r for r in state.get_regions()}

    for r_data in remote_regions:
        rid = r_data.get("region_id")
        if rid in state.tombstones:
            continue

        if rid in local_ids:
            l_reg = local_ids[rid]
            l_reg.instability = l_reg.instability * (1.0 - alpha) + r_data["instability"] * alpha
            l_reg.local_energy = l_reg.local_energy * (1.0 - alpha) + r_data.get("local_energy", 0.5) * alpha
            l_reg.integrity = max(l_reg.integrity, r_data.get("integrity", 0.5))
        else:
            r = FieldConflictRegion(
                competing_roles=r_data["competing_roles"],
                token=r_data["token"],
                instability=r_data["instability"],
                region_id=rid,
            )
            for k, v in r_data.items():
                if k not in ["competing_roles", "token", "instability", "region_id"]:
                    setattr(r, k, v)
            state.append_region(r)

    # Merge topological laws (Max)
    remote_laws = other_data.get("topological_laws", {})
    for key_str, r_val in remote_laws.items():
        pair = None
        if "|" in key_str:
            parts = key_str.split("|")
            if len(parts) == 2:
                pair = tuple(parts)
        else:
            with contextlib.suppress(ValueError):
                pair = parse_topology_key(key_str)

        if pair:
            local = state.topological_laws.get(pair, 0.0)
            merged = r_val if abs(r_val) > abs(local) else local
            state.set_topological_law(pair, merged)

    # Merge anchors
    remote_anchors = other_data.get("anchors", [])
    for a in remote_anchors:
        if len(a) == 2:
            state.record_anchor(tuple(a))

    state.record("merge", {"remote_regions": len(remote_regions)})


# ─── Clearing ───────────────────────────────────────────────────────────


def clear_topology(state: "TopologyState") -> None:
    """Clear all topology structures."""
    if state._staging is not None:
        state._staging["regions"].clear()
        state._staging["communities"].clear()
        state._staging["schema_patterns"].clear()
        state._staging["topological_laws"].clear()
        state._staging["neighborhood_cohesion"].clear()
        state._staging["impossible_neighborhoods"].clear()
        state._staging["restructuring_queue"].clear()
        state._staging["merge_success"].clear()
        state._staging["merge_attempts"].clear()
        state._staging["split_success"].clear()
        state._staging["split_attempts"].clear()
        state._staging["centrality"].clear()
        state._staging["anchors"].clear()
        state._staging["crystalline_atoms"].clear()
        state._staging["meso_clusters"].clear()
        state._staging["macro_continents"].clear()
    else:
        state._regions.clear()
        state._communities.clear()
        state._schema_patterns.clear()
        state._topological_laws.clear()
        state._neighborhood_cohesion.clear()
        state._impossible_neighborhoods.clear()
        state._restructuring_queue.clear()
        state._cohesion_merge_success.clear()
        state._cohesion_merge_attempts.clear()
        state._cohesion_split_success.clear()
        state._cohesion_split_attempts.clear()
        state._centrality.clear()
        state._anchors.clear()
        state._crystalline_atoms.clear()
        state._meso_clusters.clear()
        state._macro_continents.clear()


def clear_topology_regions(state: "TopologyState") -> None:
    """Clear only the regions list."""
    if state._staging is not None:
        state._staging["regions"].clear()
    else:
        state._regions.clear()
    state.record("clear_regions", {})
