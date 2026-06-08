"""ManifoldState — owns all role manifold state and learning data.

True ownership boundary: NO external code should mutate role_manifold,
role_compatibility, role_position_memory, or role_co_occurrence directly.
All changes go through this state object, which validates invariants.

Owns:
- role_manifold: geometric role embeddings (16-dim vectors)
- role_compatibility: legacy symbolic compatibility cache
- role_position_memory: role position distributions
- role_co_occurrence: co-occurrence counts between role-type pairs
- role_anchors: core semantic invariants (protected from drift)
- learning_count: total learning steps
- total_co_occurrences: total co-occurrence observations
"""

from collections.abc import Callable
from typing import Any

from app.transaction_context import active_transaction


class ManifoldState:
    """Sole owner of the semantic role manifold and compatibility structures."""

    def __init__(self, delta_callback: Callable[[str, str, dict], None] | None = None) -> None:
        self._delta_callback = delta_callback
        # Role embeddings: name -> 16-dim vector
        self._role_manifold: dict[str, list] = {}
        # Legacy symbolic compatibility cache: (role, type_str) -> confidence
        self._role_compatibility: dict[tuple[str, str], float] = {}
        # Position distributions per role
        self._role_position_memory: dict[str, list[float]] = {}
        # Co-occurrence: (role_a, type_a, role_b, type_b) -> count
        self._role_co_occurrence: dict[tuple[str, str, str, str], int] = {}
        # Role anchors: core semantic invariants (protected from drift)
        self._role_anchors: set[str] = set()
        # Semantic Resolution (Phase 34)
        self.dimension: int = 16
        # Sharding support (Phase 35)
        self._role_shards: dict[str, str] = {}

        # Counters
        self.learning_count: int = 0
        self.total_co_occurrences: int = 0

        # Phase 60 / 63: Linked States
        self._energy_ref: Any = None
        self._obs_ref: Any = None

        # ─── Transaction Staging ──────────────────────────────────────

    @property
    def _staging(self) -> dict | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"manifold_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"manifold_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict) -> None:
        if self._delta_callback:
            self._delta_callback("manifold", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Snapshot current state for staging."""
        self._staging = {
            "role_manifold": {k: list(v) for k, v in self._role_manifold.items()},
            "role_compatibility": dict(self._role_compatibility),
            "role_position_memory": {k: list(v) for k, v in self._role_position_memory.items()},
            "role_co_occurrence": dict(self._role_co_occurrence),
            "role_anchors": set(self._role_anchors),
            "role_shards": dict(self._role_shards),
            "dimension": self.dimension,
            "learning_count": self.learning_count,
            "total_co_occurrences": self.total_co_occurrences,
        }

    def commit(self) -> None:
        """Apply staged changes."""
        if self._staging is not None:
            self._role_manifold = self._staging["role_manifold"]
            self._role_compatibility = self._staging["role_compatibility"]
            self._role_position_memory = self._staging["role_position_memory"]
            self._role_co_occurrence = self._staging["role_co_occurrence"]
            self._role_anchors = self._staging["role_anchors"]
            self._role_shards = self._staging["role_shards"]
            self.dimension = self._staging["dimension"]
            self.learning_count = self._staging["learning_count"]
            self.total_co_occurrences = self._staging["total_co_occurrences"]
            self._staging = None

    def rollback(self) -> None:
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "role_manifold": "_role_manifold",
            "role_compatibility": "_role_compatibility",
            "role_position_memory": "_role_position_memory",
            "role_co_occurrence": "_role_co_occurrence",
            "role_anchors": "_role_anchors",
            "role_shards": "_role_shards",
            "learning_count": "learning_count",
            "total_co_occurrences": "total_co_occurrences",
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val) -> None:
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "role_manifold": "_role_manifold",
                "role_compatibility": "_role_compatibility",
                "role_position_memory": "_role_position_memory",
                "role_co_occurrence": "_role_co_occurrence",
                "role_anchors": "_role_anchors",
                "role_shards": "_role_shards",
                "learning_count": "learning_count",
                "total_co_occurrences": "total_co_occurrences",
            }
            setattr(self, attr_map[key], val)

    # ─── Role Manifold ───────────────────────────────────────────────────

    @property
    def role_manifold(self) -> dict[str, list]:
        return {k: list(v) for k, v in self._get_struct("role_manifold").items()}

    def get_manifold_vector(self, role: str) -> list:
        """Return a COPY of the role's vector to prevent reference aliasing."""
        vec = self._get_struct("role_manifold").get(role)
        if vec is not None:
            return list(vec)
        return []

    def set_manifold_vector(self, role: str, vector: list) -> None:
        """Formally set a role's manifold vector with drift tracking (Phase 63)."""
        manifold = self._get_struct("role_manifold")

        # Track drift if obs is linked
        if self._obs_ref and role in manifold:
            old_v = manifold[role]
            import math

            displacement = math.sqrt(sum((a - b) ** 2 for a, b in zip(old_v, vector, strict=False)))
            if displacement > 1e-4:
                self._obs_ref.log_drift(role, displacement)

        manifold[role] = list(vector)
        self._set_struct("role_manifold", manifold)
        self._record(
            "set_manifold_vector",
            {"role": role, "vector": vector, "displacement": displacement if "displacement" in locals() else 0.0},
        )

    def apply_force_to_manifold(self, role: str, deltas: list, clamp: bool = True) -> None:  # noqa: FBT001, FBT002
        """Apply a delta array to a role's manifold vector with drift tracking (Phase 63)."""
        if self.is_role_anchored(role):
            return

        manifold = self._get_struct("role_manifold")
        if role not in manifold:
            manifold[role] = [0.5] * 16

        vec = list(manifold[role])
        old_v = list(vec)

        for i in range(min(len(vec), len(deltas))):
            vec[i] = vec[i] + deltas[i]

        if clamp:
            for i in range(len(vec)):
                vec[i] = max(0.0, min(1.0, vec[i]))

        displacement = 0.0
        # Phase 63: Log drift
        if self._obs_ref:
            import math

            displacement = math.sqrt(sum((a - b) ** 2 for a, b in zip(old_v, vec, strict=False)))
            if displacement > 1e-4:
                self._obs_ref.log_drift(role, displacement)

        manifold[role] = vec
        self._set_struct("role_manifold", manifold)
        self._record("apply_force_to_manifold", {"role": role, "deltas": deltas, "clamp": clamp, "displacement": displacement})

    def compute_similarity(self, role_a: str, role_b: str) -> float:
        """Geometric similarity between two roles in the manifold."""
        manifold = self._get_struct("role_manifold")
        va = manifold.get(role_a)
        vb = manifold.get(role_b)
        if not va or not vb:
            return 0.0
        sim = sum(a * b for a, b in zip(va, vb, strict=False))

        # Calibration (Phase 34): scale by dimensionality
        dim = self.dimension
        neutral = dim * 0.25
        return max(0.0, min(1.0, (sim - neutral) / (dim * 0.1)))  # type: ignore[no-any-return]

    def blend_manifold_vector(self, role: str, other_vector: list, alpha: float = 0.7, beta: float = 0.3) -> None:
        """Blend an external vector into the role's manifold vector with drift tracking (Phase 63)."""
        if self.is_role_anchored(role):
            return

        manifold = self._get_struct("role_manifold")
        if role not in manifold:
            manifold[role] = [0.5] * 16

        existing = list(manifold[role])
        new_v = list(existing)

        for i in range(min(len(existing), len(other_vector))):
            new_v[i] = existing[i] * alpha + other_vector[i] * beta
            new_v[i] = max(0.0, min(1.0, new_v[i]))

        displacement = 0.0
        # Phase 63: Log drift
        if self._obs_ref:
            import math

            displacement = math.sqrt(sum((a - b) ** 2 for a, b in zip(existing, new_v, strict=False)))
            if displacement > 1e-4:
                self._obs_ref.log_drift(role, displacement)

        manifold[role] = new_v
        self._set_struct("role_manifold", manifold)
        self._record(
            "blend_manifold_vector",
            {"role": role, "other_vector": other_vector, "alpha": alpha, "beta": beta, "displacement": displacement},
        )

    def has_manifold_role(self, role: str) -> bool:
        return role in self._get_struct("role_manifold")

    def get_manifold_roles(self) -> list[str]:
        return list(self._get_struct("role_manifold").keys())

    def remove_manifold_role(self, role: str) -> None:
        if self.is_role_anchored(role):
            return

        manifold = self._get_struct("role_manifold")
        if role in manifold:
            del manifold[role]
            self._set_struct("role_manifold", manifold)
            self._record("remove_manifold_role", {"role": role})

    def prune_manifold(self, instability_map: dict, threshold: float = 0.8) -> int:
        """Remove highly unstable roles (Phase 29)."""
        manifold = self._get_struct("role_manifold")
        pruned = 0
        for role in list(manifold.keys()):
            if self.is_role_anchored(role):
                continue
            if (role.startswith("hypo_") or role == "_unidentified") and instability_map.get(role, 0.0) > threshold:
                del manifold[role]
                pruned += 1
        if pruned > 0:
            self._set_struct("role_manifold", manifold)
            self._record("prune_manifold", {"pruned": pruned})
        return pruned

    # ─── Invariant Anchoring (Phase 30) ──────────────────────────────────

    @property
    def role_anchors(self) -> set[str]:
        return set(self._get_struct("role_anchors"))

    def anchor_role(self, role: str) -> None:
        anchors = self._get_struct("role_anchors")
        anchors.add(role)
        self._set_struct("role_anchors", anchors)
        self._record("anchor_role", {"role": role})

    def unanchor_role(self, role: str) -> None:
        anchors = self._get_struct("role_anchors")
        if role in anchors:
            anchors.remove(role)
            self._set_struct("role_anchors", anchors)
            self._record("unanchor_role", {"role": role})

    def is_role_anchored(self, role: str) -> bool:
        return role in self._get_struct("role_anchors")

    # ─── Semantic Sharding (Phase 35) ────────────────────────────────────

    def shard_manifold(self, community_list: list[set[str]]) -> None:
        """Assign roles to shards based on community clusters (Phase 35)."""
        shards = self._get_struct("role_shards")
        shards.clear()

        for idx, community in enumerate(community_list):
            shard_id = f"shard_{idx}"
            for role in community:
                shards[role] = shard_id

        self._set_struct("role_shards", shards)
        self._record("shard_manifold", {"shard_count": len(community_list)})

    def get_shards(self) -> set[str]:
        return set(self._get_struct("role_shards").values())

    def get_shard_roles(self, shard_id: str) -> list[str]:
        shards = self._get_struct("role_shards")
        return [r for r, s in shards.items() if s == shard_id]

    def get_role_shard(self, role: str) -> str | None:
        return self._get_struct("role_shards").get(role)  # type: ignore[no-any-return]

    def rebalance_shards(self, max_shard_size: int = 50) -> None:
        """Monitor shard density and split oversized shards (Phase 35)."""
        shards = self._get_struct("role_shards")
        shard_counts: dict[str, list[str]] = {}
        for role, sid in shards.items():
            shard_counts.setdefault(sid, []).append(role)

        modified = False
        for sid, roles in shard_counts.items():
            if len(roles) > max_shard_size:
                # Split oversized shard
                # Simple split for now; future: use geometric clustering
                for idx, role in enumerate(roles):
                    sub_idx = idx // max_shard_size
                    if sub_idx > 0:
                        shards[role] = f"{sid}_sub{sub_idx}"
                        modified = True

        if modified:
            self._set_struct("role_shards", shards)
            self._record("rebalance_shards", {"reason": "oversized"})

    def expand_dimensions(self, new_dim: int) -> None:
        """Increase the dimensionality of the manifold (Phase 34)."""
        current_dim = self.dimension
        if new_dim <= current_dim:
            return

        manifold = self._get_struct("role_manifold")
        for role in manifold:
            vec = manifold[role]
            # Pad with neutral values (0.5)
            padding = [0.5] * (new_dim - current_dim)
            manifold[role] = vec + padding

        self.dimension = new_dim
        self._set_struct("role_manifold", manifold)
        if self._staging is not None:
            self._staging["dimension"] = new_dim

        self._record("expand_dimensions", {"new_dim": new_dim})

    def get_manifold_checksum(self) -> str:
        """Compute a geometric checksum of the entire manifold (Phase 31)."""
        import hashlib

        manifold = self._get_struct("role_manifold")
        roles = sorted(manifold.keys())
        hasher = hashlib.sha256()
        for role in roles:
            vec = manifold[role]
            # Use rounded values to avoid tiny float diffs across architectures
            vec_str = ",".join([f"{v:.4f}" for v in vec])
            hasher.update(f"{role}:{vec_str}".encode())
        return hasher.hexdigest()

    # ─── Role Compatibility (Legacy Cache) ───────────────────────────────

    @property
    def role_compatibility(self) -> dict[tuple[str, str], float]:
        return dict(self._get_struct("role_compatibility"))

    def get_compatibility(self, role: str, type_str: str) -> float:
        return self._get_struct("role_compatibility").get((role, type_str), 0.5)  # type: ignore[no-any-return]

    def set_compatibility(self, role: str, type_str: str, value: float) -> None:
        compat = self._get_struct("role_compatibility")
        compat[(role, type_str)] = max(0.0, min(1.0, value))
        self._set_struct("role_compatibility", compat)
        self._record("set_compatibility", {"role": role, "type_str": type_str, "value": value})

    def clear_compatibility(self) -> None:
        self._set_struct("role_compatibility", {})
        self._record("clear_compatibility", {})

    def clear_compatibility_for_key(self, key: tuple) -> None:
        compat = self._get_struct("role_compatibility")
        compat.pop(key, None)
        self._set_struct("role_compatibility", compat)
        self._record("clear_compatibility_for_key", {"key": key})

    # ─── Role Position Memory ────────────────────────────────────────────

    @property
    def role_position_memory(self) -> dict[str, list[float]]:
        return {k: list(v) for k, v in self._get_struct("role_position_memory").items()}

    @role_position_memory.setter
    def role_position_memory(self, value: dict[str, list[float]]) -> None:
        self._set_struct("role_position_memory", {k: list(v) for k, v in value.items()})

    # ─── Controlled Setters for Counters ──────────────────────────────────
    # These route through _set_struct for transaction staging compliance,
    # preventing external code from bypassing staging via direct attribute
    # writes.

    def set_learning_count(self, value: int) -> None:
        self._set_struct("learning_count", max(0, value))
        self._record("set_learning_count", {"value": value})

    def set_total_co_occurrences(self, value: int) -> None:
        self._set_struct("total_co_occurrences", max(0, value))
        self._record("set_total_co_occurrences", {"value": value})

    # ─── Co-Occurrence ───────────────────────────────────────────────────

    @property
    def role_co_occurrence(self) -> dict[tuple[str, str, str, str], int]:
        return dict(self._get_struct("role_co_occurrence"))

    def increment_co_occurrence(self, key: tuple, delta: int = 1) -> None:
        struct = self._get_struct("role_co_occurrence")
        struct[key] = struct.get(key, 0) + delta
        self._set_struct("role_co_occurrence", struct)
        self._record("increment_co_occurrence", {"key": key, "delta": delta})
        if self._staging is not None:
            self._staging["total_co_occurrences"] += delta
        else:
            self.total_co_occurrences += delta

    def get_co_occurrence(self, key: tuple) -> int:
        return self._get_struct("role_co_occurrence").get(key, 0)  # type: ignore[no-any-return]

    def get_role_certainty(self, role: str) -> float:
        """Compute the stability of a specific role vector based on variance (Phase 52)."""
        vec = self.get_manifold_vector(role)
        if not vec:
            return 0.0
        n_vec = len(vec)
        avg = sum(vec) / n_vec
        var = sum((x - avg) ** 2 for x in vec) / n_vec
        # Scale variance to [0,1] stability. High variance = lower stability.
        return max(0.0, min(1.0, 1.0 - var * 4.0))  # type: ignore[no-any-return]

    def get_certainty(self) -> float:
        """Global manifold certainty score."""
        manifold = self.role_manifold
        if not manifold:
            return 0.0
        total_c = sum(self.get_role_certainty(r) for r in manifold)
        return total_c / len(manifold)

    # ─── Decay ───────────────────────────────────────────────────────────

    def decay_compatibilities(self, rate: float = 0.01) -> None:
        """Decay role compatibilities toward maximum uncertainty (0.5)."""
        compat = self._get_struct("role_compatibility")
        for key in list(compat.keys()):
            current = compat[key]
            compat[key] = current + (0.5 - current) * rate
        self._set_struct("role_compatibility", compat)
        self._record("decay_compatibilities", {"rate": rate})

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "role_manifold": dict(self._role_manifold),
            "role_compatibility": {f"{k[0]}|{k[1]}": v for k, v in self._role_compatibility.items()},
            "role_position_memory": dict(self._role_position_memory),
            "role_co_occurrence": {"|".join(k): v for k, v in self._role_co_occurrence.items()},
            "role_anchors": list(self._role_anchors),
            "role_shards": dict(self._role_shards),
            "dimension": self.dimension,
            "learning_count": self.learning_count,
            "total_co_occurrences": self.total_co_occurrences,
        }

    def from_dict(self, data: dict) -> None:
        self.clear()
        self._role_manifold = {k: list(v) for k, v in data.get("role_manifold", {}).items()}
        for k, v in data.get("role_compatibility", {}).items():
            if "|" in k:
                parts = k.split("|")
                self._role_compatibility[tuple(parts)] = v
        self._role_position_memory = {k: list(v) for k, v in data.get("role_position_memory", {}).items()}
        for k, v in data.get("role_co_occurrence", {}).items():
            parts = k.split("|")
            if len(parts) == 4:
                self._role_co_occurrence[tuple(parts)] = v
        self._role_anchors = set(data.get("role_anchors", []))
        self._role_shards = dict(data.get("role_shards", {}))
        self.dimension = data.get("dimension", 16)
        self.learning_count = data.get("learning_count", 0)
        self.total_co_occurrences = data.get("total_co_occurrences", 0)

    def clear(self) -> None:
        self._set_struct("role_manifold", {})
        self._set_struct("role_compatibility", {})
        self._set_struct("role_position_memory", {})
        self._set_struct("role_co_occurrence", {})
        self._set_struct("role_anchors", set())
        self._set_struct("role_shards", {})
        self._set_struct("learning_count", 0)
        self._set_struct("total_co_occurrences", 0)
        if self._staging is not None:
            self._staging["dimension"] = 16
        else:
            self.dimension = 16

    def merge(self, other_data: dict, alpha: float = 0.5) -> None:
        """Merge remote manifold state into local (Phase 32 / 60)."""
        remote_manifold = other_data.get("role_manifold", {})

        # Phase 60: Semantic Conflict Arbitration
        # Use schema instability as a reliability weight
        remote_inst = other_data.get("schema_instability", {})

        for role, r_vec in remote_manifold.items():
            if self.is_role_anchored(role):
                continue

            if self.has_manifold_role(role):
                # Arbitration heuristic: more stable nodes have higher weight
                l_inst = (
                    self.__dict__.get("_energy_ref", {}).get_schema_instability(role) if hasattr(self, "_energy_ref") else 0.5
                )
                r_inst = remote_inst.get(role, 0.5)

                # reliability = 1 - instability  # noqa: ERA001, RUF100
                l_rel = 1.0 - l_inst
                r_rel = 1.0 - r_inst

                # Effective alpha is a blend of causal alpha and relative reliability
                # (If remote is more reliable, increase its weight)
                rel_ratio = r_rel / (l_rel + r_rel) if (l_rel + r_rel) > 0 else 0.5
                effective_alpha = alpha * 0.7 + rel_ratio * 0.3

                self.blend_manifold_vector(role, r_vec, alpha=1.0 - effective_alpha, beta=effective_alpha)
            else:
                self.set_manifold_vector(role, r_vec)

        # Merge co-occurrences (Max — avoids double-counting overlapping
        # observations)
        remote_co = other_data.get("role_co_occurrence", {})
        co_occ = self._get_struct("role_co_occurrence")
        for key_str, r_val in remote_co.items():
            parts = key_str.split("|")
            if len(parts) == 4:
                key = tuple(parts)
                co_occ[key] = max(co_occ.get(key, 0), r_val)
        self._set_struct("role_co_occurrence", co_occ)

        # Merge anchors
        remote_anchors = other_data.get("role_anchors", [])
        for r in remote_anchors:
            self.anchor_role(r)

        self.learning_count = max(self.learning_count, other_data.get("learning_count", 0))
        self._record("merge", {"alpha": alpha, "remote_roles": len(remote_manifold)})
