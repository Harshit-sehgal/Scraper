"""Shared topology types — snapshot dataclasses, exceptions, and helpers.

Ownership boundary: NO external code should mutate field_regions,
global_communities, schema_patterns, topological_laws, or cohesion
structures directly. All topology changes go through TopologyState.

This module owns the immutable read-model types and low-level helpers
extracted from the larger topology_state module.
"""

import ast
from dataclasses import dataclass


def parse_topology_key(raw: str) -> tuple[str, str]:
    if len(raw) > 1_000_000:
        msg = f"Topology key too large: {len(raw)} chars"
        raise ValueError(msg)
    try:
        value = ast.literal_eval(raw)  # nosec
    except (SyntaxError, ValueError, TypeError):
        msg = f"Invalid topology key format: {raw!r}"
        raise ValueError(msg) from None

    if not isinstance(value, tuple) or len(value) != 2 or not all(isinstance(item, str) for item in value):
        msg = f"Invalid topology key structure: {raw!r}"
        raise ValueError(msg)

    return value


class ConflictError(Exception):
    """Raised when an optimistic concurrency conflict is detected."""


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


# ─── RegionSnapshot: Immutable Read-Only View ──────────────────────────────


@dataclass(frozen=True)
class RegionSnapshot:
    """Frozen, immutable representation of a field region for read-only access.

    This is the ONLY way external code should read region data.
    FieldConflictRegion dataclass instances are mutable — never expose them directly.
    """

    region_id: str
    token: str
    competing_roles: tuple
    instability: float
    local_energy: float
    integrity: float
    recurrence_score: float
    persistence: float
    semantic_pressure: float
    stability_momentum: float
    # thermodynamic potential = local_energy - local_temperature * instability
    free_energy: float
    local_convergence: float
    local_temperature: float
    source_record: str
    domain: str
    version: int  # For validation


@dataclass(frozen=True)
class EdgeFieldSnapshot:
    """Unified read model for role-pair topology forces.

    This is derived from topology-owned structures only. It does not create a
    second edge authority; it makes existing cohesion / law / region pressure
    observable through one bounded field representation.
    """

    source: str
    target: str
    affinity: float
    repulsion: float
    uncertainty: float
    route_strength: float
    pressure: float
    law: float
    cohesion: float
    impossible: bool
    semantics: str


@dataclass(frozen=True)
class MesoClusterSnapshot:
    """Active meso-scale semantic entity — first-class field structure.

    Unlike the previous passive summary dict, this carries its own
    dynamic properties (pressure, entropy, drift, stability) and
    governs its constituent regions through cross-scale feedback.

    Meso clusters are the intermediate scale between micro (regions)
    and macro (continents). They form naturally from shared roles
    and exert top-down stabilization / perturbation on their regions.
    """

    cluster_id: str
    size: int
    region_ids: tuple
    tokens: tuple
    shared_roles: tuple
    all_roles: tuple
    avg_instability: float
    avg_convergence: float
    avg_pressure: float
    # Active entity properties
    entropy: float  # internal disorder
    drift: float  # how much the cluster's center is moving
    stability: float  # inverse of avg instability, smoothed
    boundary_strength: float  # 0=porous, 1=tightly bounded
    interaction_policy: str  # "cooperative", "competitive", "neutral", "isolated"
    centroid: tuple  # center of mass in role space
    version: int = 1


@dataclass(frozen=True)
class MacroContinentSnapshot:
    """Macro-scale semantic continent — large-scale field structure.

    Continents group related meso clusters into the largest scale of
    organization. They provide long-range guidance, preserve diversity,
    and prevent monopolistic attractors from dominating the field.

    Properties:
    - pressure: Top-down governance pressure on constituent meso clusters
    - entropy: Diversity of meso clusters within the continent
    - stability: Long-term structural persistence
    - guidance_strength: How strongly the continent influences its clusters
    - diversity_pressure: Mechanism to prevent single-attractor dominance
    """

    continent_id: str
    size: int  # total regions across all constituent clusters
    meso_cluster_ids: tuple
    all_roles: tuple
    pressure: float
    entropy: float
    stability: float
    convergence: float
    guidance_strength: float  # how strongly this continent influences meso
    diversity_pressure: float  # 0=monoculture risk, 1=max diversity
    centroid: tuple  # center of mass
    version: int = 1
