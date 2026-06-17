"""Role Embedding Engine.
=====================

Learns and maintains geometric role embeddings within a topological manifold.
Meaning is derived from similarity and stable field motifs.
"""

import concurrent.futures
import contextlib
import logging
import threading
from dataclasses import dataclass
from typing import Any

from app.semantic_ir import (
    SemanticGraph,
    SemanticToken,
    SemanticType,
)
from app.semantic_world_state import get_world_state

logger = logging.getLogger(__name__)


class RoleEmbeddingEngine:
    """Learns role embeddings from global field dynamics and stable motifs."""

    def __init__(self) -> None:
        self._ws = None
        # Ephemeral force buffer for manifold relaxation
        self.force_buffer: dict[str, list[float]] = {}
        # Thread-safety lock for shared manifold_copy mutations across shards
        self._relax_lock = threading.Lock()
        self._seed_baseline_manifold()

    @property
    def ws(self):
        if self._ws is not None:
            return self._ws
        import app.semantic_world_state

        return app.semantic_world_state.get_world_state()

    @ws.setter
    def ws(self, value) -> None:
        self._ws = value

    def _seed_baseline_manifold(self) -> None:
        if self.manifold:
            return
        from app.field_laws import ROLE_EXCLUSIVITY
        from app.semantic_allocation_engine import _UNIVERSAL_ROOTS

        seeded = set()
        for ra, rb in ROLE_EXCLUSIVITY:
            for role in (ra, rb):
                if role not in seeded:
                    seeded.add(role)
                    best_type = SemanticType.TEXT
                    for roots, stype in _UNIVERSAL_ROOTS:
                        if any(root in role.lower() for root in roots):
                            best_type = stype
                            break
                    vec = self._get_type_vector(best_type)
                    # Dampen baseline toward neutral to leave room for learning
                    # Phase 71: Add tiny random jitter to prevent exact
                    # manifold collapse
                    import random

                    for i in range(len(vec)):
                        jitter = (random.random() - 0.5) * 0.01  # nosec B311
                        vec[i] = max(0.0, min(1.0, vec[i] * 0.85 + 0.5 * 0.15 + jitter))
                    self.ws.set_manifold_vector(role, vec)

    @property
    def manifold(self) -> dict[str, list[float]]:
        return self.ws.role_manifold  # type: ignore[no-any-return]

    @property
    def learning_count(self) -> int:
        return self.ws.learning_count  # type: ignore[no-any-return]

    @learning_count.setter
    def learning_count(self, value: int) -> None:
        self.ws.learning_count = value

    @property
    def compatibility_cache(self) -> dict[tuple[str, str], float]:
        """Legacy access to symbolic compatibility dict."""
        return self.ws.role_compatibility  # type: ignore[no-any-return]

    @property
    def co_occurrence(self) -> dict[tuple[str, str, str, str], int]:
        return self.ws.role_co_occurrence  # type: ignore[no-any-return]

    @property
    def total_co_occurrences(self) -> int:
        return self.ws.total_co_occurrences  # type: ignore[no-any-return]

    @total_co_occurrences.setter
    def total_co_occurrences(self, value: int) -> None:
        self.ws.total_co_occurrences = value

    def get_compatibility(self, role: str, stype: SemanticType, token: SemanticToken | None = None) -> float:
        """Geometric compatibility: dot product in the role manifold."""
        role_vec = self.manifold.get(role)
        if not role_vec:
            # Cold start: fallback to legacy cache or default
            type_str = stype.value if hasattr(stype, "value") else str(stype)
            return self.compatibility_cache.get((role, type_str), 0.5)

        # Use token embedding if available and sufficiently differentiated
        if token and hasattr(token, "embedding") and any(v != 0.5 for v in token.embedding):
            type_vec = token.embedding
        else:
            type_vec = self._get_type_vector(stype)

        # Similarity = dot product
        sim = sum(rv * tv for rv, tv in zip(role_vec, type_vec, strict=False))

        # Theoretical max sim for this specific role-type combination
        is_role_core = role_vec[-1] > 0.7
        is_type_core = type_vec[-1] > 0.7

        # Phase 34: Dynamic normalization based on dimensionality
        dim = self.dimension
        neutral = dim * 0.25
        # Baseline: slightly above neutral
        baseline = neutral + 0.25
        # Core max contribution: 1.0 (both), 0.5 (one), 0.25 (neither)
        core_max = 1.0 if (is_role_core and is_type_core) else (0.25 if not is_role_core and not is_type_core else 0.5)
        theoretical_max = baseline + core_max

        if sim >= theoretical_max:
            result = 1.0
        elif sim <= baseline:
            result = 0.0
        else:
            result = (sim - baseline) / (theoretical_max - baseline)

        # 3. Structural Bridges (Law 1 - Meaning from Topology)
        # Codes are often used as abbreviations for Locations or Organizations.
        # This provides a cold-start bridge for structural roles.
        if stype == SemanticType.CODE:
            # Simple root check to avoid recursion with _infer_role_type
            structural_roots = ["loc", "city", "addr", "place", "dest", "orig", "nam", "comp", "firm", "brand"]
            role_lower = role.lower()
            if any(r in role_lower for r in structural_roots):
                # Baseline 0.6 for structural codes matching structural roles
                result = max(result, 0.6)

        return result

    def get_learned_exclusion(self, role_a: str, role_b: str) -> float:
        """Topological exclusion: delegates to WorldState geometry."""
        return self.ws.get_derived_exclusion(role_a, role_b)  # type: ignore[no-any-return]

    def get_role_similarity(self, role_a: str, role_b: str) -> float:
        """Geometric similarity between two roles in the manifold."""
        va = self.manifold.get(role_a)
        vb = self.manifold.get(role_b)
        if not va or not vb:
            return 0.0

        sim = sum(a * b for a, b in zip(va, vb, strict=False))

        # Calibration (Phase 34): scale by dimensionality
        dim = self.dimension
        neutral = dim * 0.25
        return max(0.0, min(1.0, (sim - neutral) / (dim * 0.1)))

    @property
    def dimension(self) -> int:
        return self.ws.manifold_dimension  # type: ignore[no-any-return]

    def _get_type_vector(self, stype: SemanticType) -> list[float]:
        """Returns a canonical vector representing a SemanticType."""
        dim = self.dimension
        vec = [0.5] * dim
        type_idx = {
            SemanticType.PRICE: 0,
            SemanticType.DATE: 1,
            SemanticType.LOCATION: 2,
            SemanticType.ORGANIZATION: 3,
            SemanticType.PHONE: 4,
            SemanticType.EMAIL: 5,
            SemanticType.URL: 6,
            SemanticType.NUMBER: 7,
            SemanticType.RATING: 8,
            SemanticType.DURATION: 9,
            SemanticType.CODE: 10,
            SemanticType.NAME: 11,
            SemanticType.TEXT: 12,
            SemanticType.IDENTIFIER: 13,
        }.get(stype)
        if type_idx is not None and type_idx < dim:
            vec[type_idx] = 1.0

        # Topological Neutrality: dimension dim-2 (centrality) is 0.0 for seeds
        if dim >= 2:
            vec[-2] = 0.0

        # Core Entity Bias: seeds for structural types are anchored in the last
        # dimension
        is_core = (
            1.0 if stype in [SemanticType.PRICE, SemanticType.DATE, SemanticType.LOCATION, SemanticType.ORGANIZATION] else 0.5
        )
        vec[-1] = is_core

        return vec

    def get_adaptive_rate(self, base_rate: float = 0.1) -> float:
        """Compute learning rate modulated by field pressure (Phase 62).

        High Pressure = Faster learning (search).
        Low Pressure = Slower learning (precision).
        """
        pressure = 0.5
        with contextlib.suppress(AttributeError):
            pressure = self.ws.get_system_pressure()

        certainty = self.get_certainty()
        # Scale by pressure [0.5, 2.0] and stability (1.0 - certainty)
        return base_rate * (0.5 + pressure * 1.5) * (1.0 - certainty)

    def learn_from_allocation(
        self,
        role: str,
        token_type: SemanticType,
        _token_raw: str,
        success: bool,
        delta: float = 0.05,
        coherence: float = 1.0,
    ) -> None:
        """Apply learning force directly to the manifold."""
        if coherence < 0.6:
            return

        # Identity Protection Law: only reinforce if types are compatible
        from app.semantic_allocation_engine import _infer_role_type

        ideal_type = _infer_role_type(role)
        is_compatible = (
            token_type in (ideal_type, SemanticType.TEXT) or ideal_type == SemanticType.TEXT or token_type == SemanticType.CODE
        )

        if success and not is_compatible:
            return

        if not success and not self.ws.has_manifold_role(role):
            return

        # Initialize role vector if missing
        if not self.ws.has_manifold_role(role):
            self.ws.set_manifold_vector(role, self._get_type_vector(ideal_type))

        # Phase 66: Semantic Saturation (Attractor Skeletonization)
        # Skip learning if role is extremely stable to reduce churn and journal
        # bloat
        certainty = self.ws._manifold.get_role_certainty(role)
        if success and certainty > 0.98 and delta < 0.1:  # Increased breakthrough threshold
            return

        role_vec = self.ws.get_manifold_vector(role)
        type_vec = self._get_type_vector(token_type)

        effective_delta = delta if success else -delta
        # Dynamic Learning Rate (Phase 62): now adaptive to field pressure
        rate = self.get_adaptive_rate()

        # Apply learning force directly to the manifold
        dim = self.dimension
        for i in range(dim):
            role_vec[i] = max(0.0, min(1.0, role_vec[i] + (type_vec[i] - role_vec[i]) * effective_delta * rate))

        self.ws.set_manifold_vector(role, role_vec)
        self.learning_count += 1

    def apply_motif_gravity(self, role_name: str, primary_type: SemanticType, stability: float) -> None:
        """Accumulate gravity force from stable motifs."""
        if stability < 0.1:
            return

        if not self.ws.has_manifold_role(role_name):
            from app.semantic_allocation_engine import _infer_role_type

            self.ws.set_manifold_vector(role_name, self._get_type_vector(_infer_role_type(role_name)))

        role_vec = self.ws.get_manifold_vector(role_name)
        type_vec = self._get_type_vector(primary_type)

        # Gravity Strength: proportional to motif stability
        gravity = 0.05 * stability * (1.0 - self.get_certainty())

        # Accumulate force vector
        dim = self.dimension
        force = self.force_buffer.setdefault(role_name, [0.0] * dim)
        for i in range(dim):
            force[i] += (type_vec[i] - role_vec[i]) * gravity

    def relax_manifold(self) -> None:
        """Geometric relaxation of the Role Manifold with Semantic Sharding (Phase 35)."""
        manifold_copy = self.manifold
        if not manifold_copy:
            return

        all_roles = list(manifold_copy.keys())
        shards = self.ws.get_shards()

        # Phase 34: Cognitive Elasticity — scale rate by system pressure
        try:
            pressure = self.ws.get_system_pressure()
            policy = self.ws._observability.get_stability_policy(self.ws.capture_governance_snapshot())
        except AttributeError:
            pressure = 1.0  # Fallback
            policy = {"propagation_damping": 1.0}

        damping = policy.get("propagation_damping", 1.0)
        base_rate = 0.02 * (1.0 - self.get_certainty()) * (0.5 + pressure) * damping

        # Thread-safety lock for shared manifold_copy mutations across shards —
        # initialized in __init__
        def _relax_roles_safe(roles, manifold_full, rate) -> None:
            """Wrapper that locks shared manifold mutations."""
            with self._relax_lock:
                self._relax_roles(roles, manifold_full, rate)

        if not shards:
            # Fallback to monolithic relaxation
            self._relax_roles(all_roles, manifold_copy, base_rate)
        else:
            # Phase 35: Parallel Relaxation Engine — now thread-safe
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for shard_id in shards:
                    shard_roles = self.ws.get_shard_roles(shard_id)
                    futures.append(executor.submit(_relax_roles_safe, shard_roles, manifold_copy, base_rate))
                # Wait for all shards to complete
                concurrent.futures.wait(futures)

        # Clear buffer after integration (Phase 1 across all shards)
        self.force_buffer.clear()

        # Save mutated copies back
        for role, vec in manifold_copy.items():
            self.ws.set_manifold_vector(role, vec)

        # Sync legacy compatibility cache
        for role in all_roles:
            for stype in SemanticType:
                type_str = stype.value if hasattr(stype, "value") else str(stype)
                self.ws.set_compatibility(role, type_str, self.get_compatibility(role, stype))

        self.detect_dimensionality_need()

    def _relax_roles(self, roles: list[str], manifold_full: dict[str, Any], base_rate: float) -> None:
        """Internal helper for localized relaxation of a subset of roles."""
        # 1. Filter out anchored roles
        roles = [r for r in roles if not self.ws.is_role_anchored(r)]
        if not roles:
            return

        # Phase 0: Calculate Role-specific Hysteresis (Solidification)
        hysteresis = {}
        for r in roles:
            instability = self.ws.metrics.schema_instability.get(r, 0.5)
            stability = max(0.0, 1.0 - instability)
            hysteresis[r] = 1.0 - (stability**2) * 0.9

        # Phase 1: Apply accumulated forces
        for role in roles:
            force = self.force_buffer.get(role)
            if force:
                h = hysteresis.get(role, 1.0)
                vec = manifold_full[role]
                for k in range(self.dimension):
                    vec[k] = max(0.0, min(1.0, vec[k] + force[k] * h))

        # Phase 2: Repulsion (Contrastive Repulsion Law)
        if len(roles) >= 2:
            for i in range(len(roles)):
                for j in range(i + 1, len(roles)):
                    ra, rb = roles[i], roles[j]
                    exclusion = self.ws.get_derived_exclusion(ra, rb)
                    if exclusion > 0.3:
                        vec_a = manifold_full[ra]
                        vec_b = manifold_full[rb]
                        h_a, h_b = hysteresis.get(ra, 1.0), hysteresis.get(rb, 1.0)
                        for k in range(self.dimension):
                            diff = vec_a[k] - vec_b[k]
                            force = exclusion * 0.1 * base_rate * h_a * h_b
                            vec_a[k] = max(0.0, min(1.0, vec_a[k] + diff * force))
                            vec_b[k] = max(0.0, min(1.0, vec_b[k] - diff * force))

        # Phase 3: Attraction (Affinity Attraction Law)
        # Note: only within-shard cohesion is considered here
        for key, cohesion in self.ws.neighborhood_cohesion.items():
            ra, rb = key
            if ra in roles and rb in roles and cohesion > 0.6:
                vec_a = manifold_full[ra]
                vec_b = manifold_full[rb]
                h_a, h_b = hysteresis.get(ra, 1.0), hysteresis.get(rb, 1.0)
                for k in range(self.dimension):
                    diff = vec_b[k] - vec_a[k]
                    force = (cohesion - 0.5) * 0.1 * base_rate * h_a * h_b
                    vec_a[k] = max(0.0, min(1.0, vec_a[k] + diff * force))
                    vec_b[k] = max(0.0, min(1.0, vec_b[k] - diff * force))

        # Phase 4: Re-Alignment (Restoring Force)
        from app.semantic_allocation_engine import _infer_role_type

        for role in roles:
            seed_type = _infer_role_type(role)
            seed_vec = self._get_type_vector(seed_type)
            role_vec = manifold_full[role]
            h = hysteresis.get(role, 1.0)

            for k in range(self.dimension):
                diff = seed_vec[k] - role_vec[k]
                force = 0.005 * (1.0 - h) * base_rate
                role_vec[k] = max(0.0, min(1.0, role_vec[k] + diff * force))

        # Phase 5: Intent Steering (Phase 36)
        # Apply force toward user-defined cognitive goals
        active_intents = self.ws.active_intents
        for details in active_intents.values():
            target_vec = details["target_vec"]
            strength = details["strength"]
            target_roles = details.get("target_roles", [])

            # Pad target_vec if dimensionality has expanded
            if len(target_vec) < self.dimension:
                target_vec = target_vec + [0.5] * (self.dimension - len(target_vec))

            for role in roles:
                # Apply intent if either:
                # 1. target_roles is empty (global intent)
                # 2. role is explicitly targeted
                if not target_roles or role in target_roles:
                    role_vec = manifold_full[role]
                    # Intent force is scaled by strength and base_rate
                    for k in range(self.dimension):
                        diff = target_vec[k] - role_vec[k]
                        # Strength 1.0 = full attractor pull
                        force = diff * strength * 0.1 * base_rate
                        role_vec[k] = max(0.0, min(1.0, role_vec[k] + force))

    def learn_co_occurrence(self, assignment_a: tuple[str, ...], assignment_b: tuple[str, ...], success: bool) -> None:
        key = assignment_a + assignment_b
        self.ws.increment_co_occurrence(key, 1 if success else -1)

    def get_co_occurrence_boost(self, role_a: str, type_a: str, role_b: str, type_b: str) -> float:
        key = (role_a, type_a, role_b, type_b)
        count = self.co_occurrence.get(key, 0)
        if self.total_co_occurrences == 0:
            return 0.0
        return max(-0.1, min(0.1, count / self.total_co_occurrences))

    def propagate_co_occurrence(self, assignments: dict[str, tuple[str, str]]) -> dict[str, float]:
        boosts: dict[str, float] = {}
        items = list(assignments.items())
        for i in range(len(items)):
            role_i, (type_i, _) = items[i]
            boost = 0.0
            for j in range(len(items)):
                if i == j:
                    continue
                role_j, (type_j, _) = items[j]
                boost += self.get_co_occurrence_boost(role_i, type_i, role_j, type_j)
            boosts[role_i] = boost / max(len(items) - 1, 1)
        return boosts

    def learn_contradiction(self, role_a: str, role_b: str, token_type: str) -> None:  # noqa: ARG002, RUF100
        from app.instability_api import InstabilityAPI

        inst_api = InstabilityAPI(ws=self.ws)
        current = inst_api.get_learned_exclusion(role_a, role_b)
        inst_api.set_exclusion(role_a, role_b, min(1.0, current + 0.15))

    def get_certainty(self) -> float:
        if not self.manifold:
            return 0.0
        total_v = 0.0
        for vec in self.manifold.values():
            if not vec:
                continue
            n_vec = len(vec)
            avg = sum(vec) / n_vec
            var = sum((x - avg) ** 2 for x in vec) / n_vec
            total_v += var

        if not self.manifold:
            return 0.0
        return min(1.0, (total_v / len(self.manifold)) * 4.0)

    def get_calibrated_confidence(self, score: float) -> float:
        certainty = self.get_certainty()
        return score * (0.7 + 0.3 * certainty)

    def get_learning_speed(self) -> float:
        return min(self.learning_count / 100.0, 1.0)

    def detect_dimensionality_need(self) -> None:
        """Analyze if current semantic resolution is sufficient (Phase 34)."""
        if self.learning_count < 200:
            return

        certainty = self.get_certainty()
        # If certainty remains very low despite significant learning,
        # it indicates a crowded manifold (Semantic Collision).
        if certainty < 0.2 and self.dimension < 64:
            new_dim = self.dimension + 8
            logger.info("DIMENSIONALITY INDUCTION: Expanding manifold resolution to %s.", new_dim)
            self.ws.expand_dimensions(new_dim)

    def save_cache(self) -> dict[str, Any]:
        cache: dict[str, Any] = {}
        for (r, t), v in self.compatibility_cache.items():
            cache[f"compat:{r}:{t}"] = v
        for role, vec in self.manifold.items():
            cache[f"manifold:{role}"] = vec
        return cache

    def load_cache(self, data: dict[str, Any]) -> None:
        self.ws.clear_compatibility()
        for k, v in data.items():
            if k.startswith("compat:"):
                parts = k.split(":")
                self.ws.set_compatibility(parts[1], parts[2], v)
            elif k.startswith("manifold:"):
                role = k.split(":", 1)[1]
                self.ws.set_manifold_vector(role, v)


@dataclass
class RelationshipEmbeddingSpace:
    def compute_embedding(self, node_idx: int, graph: SemanticGraph) -> list[float]:
        ws = get_world_state()
        dim = ws.manifold_dimension

        if node_idx < len(graph.tokens):
            token = graph.tokens[node_idx]
            vec = [0.5] * dim
            type_idx = {
                SemanticType.PRICE: 0,
                SemanticType.DATE: 1,
                SemanticType.LOCATION: 2,
                SemanticType.ORGANIZATION: 3,
                SemanticType.PHONE: 4,
                SemanticType.EMAIL: 5,
                SemanticType.URL: 6,
                SemanticType.NUMBER: 7,
                SemanticType.RATING: 8,
                SemanticType.DURATION: 9,
                SemanticType.CODE: 10,
                SemanticType.NAME: 11,
                SemanticType.TEXT: 12,
                SemanticType.IDENTIFIER: 13,
            }.get(token.primary_type)

            if type_idx is not None and type_idx < dim:
                vec[type_idx] = 1.0

            if token.span and graph.tokens:
                node_edges = [e for e in graph.relationships if node_idx in (e.source_idx, e.target_idx)]
                centrality = len(node_edges) / max(len(graph.relationships), 1)
                if dim >= 2:
                    vec[-2] = centrality
                # Core Entity Bias: stable structural types have higher
                # manifold priority
                is_core = (
                    1.0
                    if token.primary_type
                    in [SemanticType.PRICE, SemanticType.DATE, SemanticType.LOCATION, SemanticType.ORGANIZATION]
                    else 0.5
                )
                vec[-1] = is_core
            return vec
        return [0.5] * dim
