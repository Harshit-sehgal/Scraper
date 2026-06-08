"""Topology Dynamics — multi-scale topology evolution functions.

EXPERIMENTAL / RESEARCH ONLY — These functions implement multi-scale
semantic topology dynamics (meso clusters, macro continents, cross-scale
pressure flow). They operate on a TopologyState instance.

Extracted from topology_state.py for modularity.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.topology_state import TopologyState

# ─── Meso Clusters ──────────────────────────────────────────────────────


def compute_meso_clusters(state: TopologyState) -> None:
    """Compute meso-scale clusters from current field regions.

    Meso clusters group regions that share competing roles, forming
    intermediate-scale structures between micro (single region) and
    macro (global aggregate). These clusters are now first-class field
    entities with their own dynamics: pressure, entropy, drift, stability,
    boundary_strength, and interaction_policy.

    LAW: Meso clustering is derived from topology itself, not from
    any external partitioning scheme.
    """
    regs = state._get_regions()
    clusters = []
    assigned: set[int] = set()

    # Retrieve previous clusters to carry forward their dynamic properties
    prev_clusters = state._get_struct("meso_clusters")
    prev_map = {}
    for pc in prev_clusters:
        rid_tuple = tuple(sorted(pc.get("region_ids", [])))
        prev_map[rid_tuple] = pc

    for i in range(len(regs)):
        if i in assigned:
            continue
        cluster_indices = [i]
        for j in range(i + 1, len(regs)):
            if j in assigned:
                continue
            shared = set(regs[i].competing_roles) & set(regs[j].competing_roles)
            if shared:
                cluster_indices.append(j)
                assigned.add(j)
        assigned.add(i)

        cluster_regions = [regs[k] for k in cluster_indices]
        if len(cluster_regions) == 1:
            continue  # Single regions are micro-scale, not meso

        avg_instability = sum(r.instability for r in cluster_regions) / len(cluster_regions)
        avg_convergence = sum(r.local_convergence for r in cluster_regions) / len(cluster_regions)
        avg_pressure = sum(r.semantic_pressure for r in cluster_regions) / len(cluster_regions)
        shared_roles = (
            list(set.intersection(*[set(r.competing_roles) for r in cluster_regions])) if len(cluster_regions) > 0 else []
        )
        all_roles = list(set.union(*[set(r.competing_roles) for r in cluster_regions]))
        tokens = list({r.token for r in cluster_regions})
        rid_tuple = tuple(sorted([r.region_id for r in cluster_regions]))
        prev = prev_map.get(rid_tuple, {})

        instabilities = [r.instability for r in cluster_regions]
        entropy = (
            sum(abs(i - sum(instabilities) / len(instabilities)) for i in instabilities) / len(instabilities)
            if len(instabilities) > 1
            else 0.0
        )

        prev_instability = prev.get("avg_instability", avg_instability)
        drift = abs(avg_instability - prev_instability)

        prev_stability = prev.get("stability", 0.5)
        raw_stability = 1.0 - avg_instability
        stability = prev_stability * 0.7 + raw_stability * 0.3

        boundary_strength = (len(shared_roles) / len(all_roles) if len(all_roles) > 0 else 0.0) if all_roles else 0.0
        prev_boundary = prev.get("boundary_strength", boundary_strength)
        boundary_strength = prev_boundary * 0.8 + boundary_strength * 0.2

        prev_policy = prev.get("interaction_policy", "neutral")
        if avg_instability > 0.7 and avg_convergence < 0.3:
            interaction_policy = "competitive"
        elif avg_convergence > 0.7 and avg_instability < 0.3:
            interaction_policy = "cooperative"
        elif boundary_strength > 0.8:
            interaction_policy = "isolated"
        else:
            interaction_policy = "neutral"
        if interaction_policy != prev_policy and abs(avg_instability - 0.5) < 0.2:
            interaction_policy = prev_policy

        role_hash = sum(hash(r) for r in all_roles) if all_roles else 0
        centroid = (role_hash / 1e10 % 1.0, sum(hash(r) * 7 for r in all_roles) / 1e10 % 1.0) if all_roles else (0.0, 0.0)
        cluster_id = prev.get("cluster_id", f"meso_{uuid.uuid4().hex[:8]}")

        clusters.append(
            {
                "cluster_id": cluster_id,
                "size": len(cluster_regions),
                "region_ids": [r.region_id for r in cluster_regions],
                "tokens": tokens,
                "shared_roles": shared_roles,
                "all_roles": all_roles,
                "avg_instability": round(avg_instability, 3),
                "avg_convergence": round(avg_convergence, 3),
                "avg_pressure": round(avg_pressure, 3),
                "entropy": round(entropy, 3),
                "drift": round(drift, 3),
                "stability": round(stability, 3),
                "boundary_strength": round(boundary_strength, 3),
                "interaction_policy": interaction_policy,
                "centroid": centroid,
            },
        )

    state._set_struct("meso_clusters", clusters)
    state._record("compute_meso_clusters", {"count": len(clusters)})


# ─── Macro Continents ───────────────────────────────────────────────────


def compute_macro_continents(state: TopologyState) -> None:
    """Compute macro-scale semantic continents from meso clusters.

    Macro continents group related meso clusters into the largest scale of
    semantic organization. They provide long-range stabilization, preserve
    diversity, and prevent monopolistic attractors from dominating.

    LAW: Macro organization emerges from meso cluster interaction,
    not from global partitioning. Continents are field-derived.
    """
    clusters = state._get_struct("meso_clusters")
    if not clusters:
        state._set_struct("macro_continents", [])
        state._record("compute_macro_continents", {"count": 0})
        return

    prev_continents = state._get_struct("macro_continents")
    prev_map = {}
    for pc in prev_continents:
        cid_tuple = tuple(sorted(pc.get("meso_cluster_ids", [])))
        prev_map[cid_tuple] = pc

    continents = []
    assigned: set[int] = set()
    for i in range(len(clusters)):
        if i in assigned:
            continue
        continent_indices = [i]
        for j in range(i + 1, len(clusters)):
            if j in assigned:
                continue
            a_roles = set(clusters[i].get("all_roles", []))
            b_roles = set(clusters[j].get("all_roles", []))
            if a_roles & b_roles:
                continent_indices.append(j)
                assigned.add(j)
        assigned.add(i)

        continent_clusters = [clusters[k] for k in continent_indices]
        all_meso_ids = tuple(sorted([c["cluster_id"] for c in continent_clusters]))
        total_size = max(sum(c["size"] for c in continent_clusters), 1)
        total_regions = sum(c["size"] for c in continent_clusters)
        all_roles = list(set.union(*[set(c.get("all_roles", [])) for c in continent_clusters]))
        pressure = sum(c["avg_pressure"] * c["size"] for c in continent_clusters) / total_size
        stability = sum(c.get("stability", 0.5) * c["size"] for c in continent_clusters) / total_size
        convergence = sum(c["avg_convergence"] * c["size"] for c in continent_clusters) / total_size

        if len(continent_clusters) > 1:
            instabilities = [c["avg_instability"] for c in continent_clusters]
            mean_inst = sum(instabilities) / len(instabilities)
            entropy = sum(abs(i - mean_inst) for i in instabilities) / len(instabilities)
        else:
            entropy = 0.0

        prev = prev_map.get(all_meso_ids, {})
        prev_guidance = prev.get("guidance_strength", 0.5)
        raw_guidance = min(1.0, stability * (1.0 + entropy) * 0.7)
        guidance_strength = prev_guidance * 0.85 + raw_guidance * 0.15

        if len(continent_clusters) > 1:
            instabilities = [c["avg_instability"] for c in continent_clusters]
            variance = sum((i - sum(instabilities) / len(instabilities)) ** 2 for i in instabilities) / len(instabilities)
            diversity_pressure = min(1.0, variance * 5.0)
        else:
            diversity_pressure = 0.0

        centroids = [c.get("centroid", (0.0, 0.0)) for c in continent_clusters]
        centroid = (
            (sum(c[0] for c in centroids) / len(centroids), sum(c[1] for c in centroids) / len(centroids))
            if centroids
            else (0.0, 0.0)
        )
        continent_id = prev.get("continent_id", f"macro_{uuid.uuid4().hex[:8]}")

        continents.append(
            {
                "continent_id": continent_id,
                "size": total_regions,
                "meso_cluster_ids": list(all_meso_ids),
                "all_roles": all_roles,
                "pressure": round(pressure, 3),
                "entropy": round(entropy, 3),
                "stability": round(stability, 3),
                "convergence": round(convergence, 3),
                "guidance_strength": round(guidance_strength, 3),
                "diversity_pressure": round(diversity_pressure, 3),
                "centroid": centroid,
            },
        )

    state._set_struct("macro_continents", continents)
    state._record("compute_macro_continents", {"count": len(continents)})


def compute_macro_from_meso(state: TopologyState) -> dict:
    """Compute macro-scale properties from meso clusters.

    Returns dict with avg_convergence, avg_instability, fragmentation,
    cluster_diversity, and pressure.
    """
    clusters = state._get_struct("meso_clusters")
    if not clusters:
        regs = state._get_regions()
        if not regs:
            return {
                "avg_convergence": 0.5,
                "avg_instability": 0.5,
                "fragmentation": 0.0,
                "cluster_diversity": 0.0,
                "pressure": 0.3,
            }
        return {
            "avg_convergence": sum(r.local_convergence for r in regs) / len(regs),
            "avg_instability": sum(r.instability for r in regs) / len(regs),
            "fragmentation": 0.0,
            "cluster_diversity": 0.0,
            "pressure": sum(r.semantic_pressure for r in regs) / len(regs),
        }

    total_size = sum(c["size"] for c in clusters)
    if total_size == 0:
        return {
            "avg_convergence": 0.5,
            "avg_instability": 0.5,
            "fragmentation": 0.0,
            "cluster_diversity": 0.0,
            "pressure": 0.3,
        }

    weighted_convergence = sum(c["avg_convergence"] * c["size"] for c in clusters) / total_size
    weighted_instability = sum(c["avg_instability"] * c["size"] for c in clusters) / total_size
    weighted_pressure = sum(c["avg_pressure"] * c["size"] for c in clusters) / total_size
    fragmentation = len(clusters) / max(total_size, 1)
    mean_inst = weighted_instability
    diversity = (
        (sum((c["avg_instability"] - mean_inst) ** 2 for c in clusters) / len(clusters)) ** 0.5 if len(clusters) > 1 else 0.0
    )

    return {
        "avg_convergence": round(weighted_convergence, 3),
        "avg_instability": round(weighted_instability, 3),
        "fragmentation": round(fragmentation, 3),
        "cluster_diversity": round(diversity, 3),
        "pressure": round(weighted_pressure, 3),
    }


# ─── Multi-Scale Evolution ──────────────────────────────────────────────


def evolve_meso_clusters(state: TopologyState) -> int:
    """Evolve meso clusters — apply cluster-level feedback to constituent regions."""
    clusters = state._get_struct("meso_clusters")
    if not clusters:
        return 0

    regs = state._get_regions()
    reg_map = {r.region_id: r for r in regs}
    affected = 0

    continents = state._get_struct("macro_continents")
    macro_pressure_map = {}
    for cont in continents:
        for cid in cont.get("meso_cluster_ids", []):
            macro_pressure_map[cid] = cont.get("pressure", 0.0)

    for cluster in clusters:
        cid = cluster["cluster_id"]
        boundary = cluster.get("boundary_strength", 0.5)
        policy = cluster.get("interaction_policy", "neutral")
        cluster_entropy = cluster.get("entropy", 0.0)
        cluster_stability = cluster.get("stability", 0.5)
        macro_pressure = macro_pressure_map.get(cid, 0.0)

        feedback_strength = cluster["avg_instability"] * (1.0 - cluster["avg_convergence"])
        if feedback_strength < 0.001:
            continue

        if policy == "isolated":
            feedback_strength *= max(0.0, 1.0 - boundary * 3.0 * 0.3)
        elif policy == "competitive":
            feedback_strength *= 1.3

        entropy_noise = 1.0 + (cluster_entropy - 0.5) * 0.5
        feedback_strength *= entropy_noise

        for rid in cluster["region_ids"]:
            r = reg_map.get(rid)
            if not r:
                continue
            if cluster_stability > 0.6:
                pull_mod = 1.2 if policy == "cooperative" else 1.0
                pull = cluster_stability * 0.05 * feedback_strength * pull_mod
                r.instability = max(0.01, r.instability - pull)
            else:
                push_mod = 1.4 if policy == "competitive" else 1.0
                push = (1.0 - cluster_stability) * 0.05 * feedback_strength * push_mod
                r.instability = min(1.0, r.instability + push)

            if macro_pressure > 0.5:
                r.instability = min(1.0, r.instability + macro_pressure * 0.01)

            base_temp_influence = cluster["avg_instability"] * 0.05
            if policy == "isolated":
                base_temp_influence *= 1.0 - boundary * 0.5
            r.local_temperature = r.local_temperature * 0.95 + base_temp_influence
            affected += 1

    if affected:
        state._record("evolve_meso_clusters", {"affected_regions": affected, "cluster_count": len(clusters)})
    return affected


def evolve_macro_continents(state: TopologyState) -> int:
    """Evolve macro continents — apply continent-level guidance to meso clusters.

    LAW: Macro governance is emergent from meso cluster dynamics,
    not procedural orchestration. Continents do not override; they modulate.
    """
    continents = state._get_struct("macro_continents")
    if not continents:
        return 0

    clusters = state._get_struct("meso_clusters")
    cluster_map = {c["cluster_id"]: c for c in clusters}
    affected = 0

    for continent in continents:
        guidance = continent.get("guidance_strength", 0.5)
        c_stability = continent.get("stability", 0.5)
        c_pressure = continent.get("pressure", 0.0)
        d_pressure = continent.get("diversity_pressure", 0.0)
        conv = continent.get("convergence", 0.5)

        if guidance < 0.05:
            continue

        for cid in continent.get("meso_cluster_ids", []):
            cluster = cluster_map.get(cid)
            if not cluster:
                continue

            if c_stability > 0.6:
                pull = (c_stability - 0.5) * guidance * 0.02
                cluster["avg_instability"] = max(0.01, cluster["avg_instability"] - pull)
                cluster["avg_convergence"] = min(1.0, cluster["avg_convergence"] + pull * 0.5)

            pressure_diff = c_pressure - cluster["avg_pressure"]
            cluster["avg_pressure"] = cluster["avg_pressure"] + pressure_diff * guidance * 0.05

            if d_pressure > 0.4:
                release = d_pressure * guidance * 0.01
                cluster["avg_instability"] = min(1.0, cluster["avg_instability"] + release)

            if conv > 0.7:
                gap = conv - cluster["avg_convergence"]
                cluster["avg_convergence"] = min(1.0, cluster["avg_convergence"] + gap * guidance * 0.03)

            affected += 1

    # Re-compute continent-level properties from updated clusters
    compute_macro_continents(state)

    if affected:
        state._record("evolve_macro_continents", {"affected_clusters": affected, "continent_count": len(continents)})
    return affected


def cross_scale_pressure_flow(state: TopologyState) -> None:
    """Orchestrate bidirectional pressure flow across all three scales.

    Flow path:
    1. Micro → Meso: Region instabilities aggregate into cluster-level pressure
    2. Meso → Micro: Cluster-level dynamics feed back to constituent regions
    3. Meso → Macro: Cluster properties aggregate into continent-level dynamics
    4. Macro → Meso: Continent-level governance shapes cluster behavior
    5. Macro → Micro: Continental stability provides long-range attractor field

    LAW: Cross-scale pressure flow is the canonical mechanism for
    multi-scale interaction. No scale bypass or procedural override.
    """
    now = time.time()

    # 1. Micro → Meso: Recompute clusters from evolved regions
    compute_meso_clusters(state)

    # 2. Meso → Micro: Apply meso feedback to regions
    meso_affected = evolve_meso_clusters(state)

    # 3. Meso → Macro: Build / update continents from evolved clusters
    compute_macro_continents(state)

    # 4. Macro → Meso: Apply continent guidance to clusters
    macro_affected = evolve_macro_continents(state)

    # 5. Re-sync: after macro guidance, recompute clusters with updated properties
    if macro_affected > 0:
        compute_meso_clusters(state)

    state._last_pressure_flow_time = now
    state._record(
        "cross_scale_pressure_flow",
        {
            "meso_feedback": meso_affected,
            "macro_guidance": macro_affected,
        },
    )
