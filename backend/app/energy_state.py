"""EnergyState — owns ALL energy and macro-state variables.

True ownership boundary: NO external code should mutate global_energy directly.
All energy changes go through this state object, which enforces conservation.

This is the canonical owner of all TopologyMetrics fields.
SemanticWorldState.metrics delegates to this object directly.

Owns: global_energy, global_entropy, exclusion_count, total_records_processed,
cumulative_density, cumulative_uncertainty, schema_instability,
_convergence, _temperature, _integrity, _smoothed_* smoothing caches.
"""

import math


from typing import Callable, Optional, Dict
from app.transaction_context import active_transaction


class EnergyState:
    """Sole owner of the semantic field's energy/macro-state variables."""

    def __init__(self, delta_callback: Optional[Callable[[str, str, dict], None]] = None):
        self._delta_callback = delta_callback
        # ─── Canonical State Variables ───────────────────────────────
        self._global_energy: float = 5.0
        self._global_entropy: float = 0.5
        self._exclusion_count: int = 0
        self._total_records_processed: int = 0
        self._cumulative_density: float = 0.0
        self._cumulative_uncertainty: float = 0.0
        self._dataset_coherence: float = 0.5
        self._schema_instability: dict = {}
        # ─── Internal Smoothed/Cached State ───────────────────────────
        self._convergence: float = 0.5
        self._temperature: float = 0.5
        self._integrity: float = 0.5
        self._smoothed_structural: float = 0.4
        self._smoothed_runtime: float = 0.3
        self._smoothed_temperature: float = 0.5
        self._stability_debt: float = 0.0
        
        # ─── Transaction Staging ──────────────────────────────────────
    @property
    def _staging(self) -> Optional[dict]:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"energy_staging_{id(self)}")
        return None
    
    @_staging.setter
    def _staging(self, value: Optional[dict]):
        tx = active_transaction.get()
        if tx is not None:
            tx[f"energy_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict):
        if self._delta_callback:
            self._delta_callback("energy", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self):
        """Snapshot current state for staging."""
        self._staging = {
            "_global_energy": self._global_energy,
            "_global_entropy": self._global_entropy,
            "_exclusion_count": self._exclusion_count,
            "_total_records_processed": self._total_records_processed,
            "_cumulative_density": self._cumulative_density,
            "_cumulative_uncertainty": self._cumulative_uncertainty,
            "_dataset_coherence": self._dataset_coherence,
            "_schema_instability": dict(self._schema_instability),
            "_convergence": self._convergence,
            "_temperature": self._temperature,
            "_integrity": self._integrity,
            "_smoothed_structural": self._smoothed_structural,
            "_smoothed_runtime": self._smoothed_runtime,
            "_smoothed_temperature": self._smoothed_temperature,
            "_stability_debt": self._stability_debt,
        }

    def commit(self):
        """Apply staged changes."""
        if self._staging is not None:
            self._global_energy = self._staging["_global_energy"]
            self._global_entropy = self._staging["_global_entropy"]
            self._exclusion_count = self._staging["_exclusion_count"]
            self._total_records_processed = self._staging["_total_records_processed"]
            self._cumulative_density = self._staging["_cumulative_density"]
            self._cumulative_uncertainty = self._staging["_cumulative_uncertainty"]
            self._dataset_coherence = self._staging["_dataset_coherence"]
            self._schema_instability = self._staging["_schema_instability"]
            self._convergence = self._staging["_convergence"]
            self._temperature = self._staging["_temperature"]
            self._integrity = self._staging["_integrity"]
            self._smoothed_structural = self._staging["_smoothed_structural"]
            self._smoothed_runtime = self._staging["_smoothed_runtime"]
            self._smoothed_temperature = self._staging["_smoothed_temperature"]
            self._stability_debt = self._staging["_stability_debt"]
            self._staging = None

    def rollback(self):
        self._staging = None

    def _get_val(self, key: str):
        # Normalize: all internal state and staging keys use underscores
        k = key if key.startswith("_") else f"_{key}"
        if self._staging is not None:
            return self._staging[k]
        return getattr(self, k)

    def _set_val(self, key: str, val):
        k = key if key.startswith("_") else f"_{key}"
        if self._staging is not None:
            self._staging[k] = val
        else:
            setattr(self, k, val)

    @property
    def stability_debt(self) -> float:
        return self._get_val("stability_debt")

    @stability_debt.setter
    def stability_debt(self, value: float):
        self._set_val("stability_debt", max(0.0, value))

    def adjust_stability_debt(self, delta: float):
        self.stability_debt = self.stability_debt + delta
        self._record("adjust_stability_debt", {"delta": delta})

    def rebalance_attractors(self, role_stabilities: Dict[str, float], threshold: float = 0.8):
        """Dissipate energy from monopolistic semantic basins (Phase 52).
        
        If a role becomes too dominant (stability > threshold), we siphons
        energy into entropy to encourage exploration.
        """
        if self.global_entropy > 0.8:
             return # Already high instability; no need for more dissipation
             
        for role, stability in role_stabilities.items():
            if stability > threshold:
                dissipation = (stability - threshold) * 2.0
                # Reduce global energy, increase entropy (potential to kinetic shift)
                cur_energy = self.global_energy
                self.set_energy(cur_energy - dissipation * 0.1)
                self.set_entropy(min(1.0, self.global_entropy + dissipation * 0.05))
                self._record("rebalance_attractor", {"role": role, "stability": stability, "dissipation": dissipation})

    def inject_diversification_entropy(self, scale: float = 0.05):
        """Inject directed entropy into the field to prevent freezing (Phase 55)."""
        cur = self.global_entropy
        boost = scale * (1.0 - cur)
        self.set_entropy(cur + boost)
        self._record("inject_diversification_entropy", {"boost": boost})

    @property
    def global_energy(self) -> float:
        return self._get_val("global_energy")

    @global_energy.setter
    def global_energy(self, value: float):
        self.set_energy(value)

    @property
    def global_entropy(self) -> float:
        return self._get_val("global_entropy")

    @global_entropy.setter
    def global_entropy(self, value: float):
        self.set_entropy(value)

    @property
    def exclusion_count(self) -> int:
        return self._get_val("exclusion_count")

    @exclusion_count.setter
    def exclusion_count(self, value: int):
        self.set_exclusion_count(value)

    @property
    def total_records_processed(self) -> int:
        return self._get_val("total_records_processed")

    @total_records_processed.setter
    def total_records_processed(self, value: int):
        self._set_val("total_records_processed", value)

    @property
    def cumulative_density(self) -> float:
        return self._get_val("cumulative_density")

    @cumulative_density.setter
    def cumulative_density(self, value: float):
        self.set_cumulative_density(value)

    @property
    def cumulative_uncertainty(self) -> float:
        return self._get_val("cumulative_uncertainty")

    @cumulative_uncertainty.setter
    def cumulative_uncertainty(self, value: float):
        self.set_cumulative_uncertainty(value)

    @property
    def dataset_coherence(self) -> float:
        return self._get_val("dataset_coherence")

    @dataset_coherence.setter
    def dataset_coherence(self, value: float):
        self._set_val("dataset_coherence", value)

    # ─── Properties (canonical derived metrics) ───────────────────────────

    @property
    def convergence(self) -> float:
        return self._get_val("_convergence")

    @property
    def temperature(self) -> float:
        return self._get_val("_temperature")

    @property
    def integrity(self) -> float:
        return self._get_val("_integrity")

    @property
    def field_pressure(self) -> float:
        norm_energy = min(self.global_energy / 10.0, 1.0)
        return max(0.0, min(1.0, (norm_energy + self.global_entropy + min(self.exclusion_count / 10.0, 1.0)) / 3.0))

    @property
    def semantic_temperature(self) -> float:
        return self._get_val("_temperature")

    @property
    def integrity_score(self) -> float:
        return self._get_val("_integrity")

    @property
    def convergence_score(self) -> float:
        return self._get_val("_convergence")

    @property
    def maturity(self) -> float:
        total = self._get_val("total_records_processed")
        if total == 0:
            return 0.5
        return min(total / 100.0, 1.0)

    @property
    def average_uncertainty(self) -> float:
        total = self._get_val("total_records_processed")
        if total <= 0:
            return 0.5
        return self._get_val("cumulative_uncertainty") / total

    @property
    def average_density(self) -> float:
        total = self._get_val("total_records_processed")
        if total <= 0:
            return 0.5
        return self._get_val("cumulative_density") / total

    # ─── Controlled Mutations — Scalars ──────────────────────────────────

    def set_energy(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("global_energy", max(0.0, min(10.0, value)))
        self._record("set_energy", {"value": value})

    def adjust_energy(self, delta: float):
        self.set_energy(self._get_val("global_energy") + delta)

    def set_entropy(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("global_entropy", max(0.0, min(1.0, value)))
        self._record("set_entropy", {"value": value})

    def set_convergence(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("_convergence", max(0.0, min(1.0, value)))
        self._record("set_convergence", {"value": value})

    def set_temperature(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("_temperature", max(0.0, min(1.0, value)))
        self._record("set_temperature", {"value": value})

    def set_integrity(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("_integrity", max(0.0, min(1.0, value)))
        self._record("set_integrity", {"value": value})

    def set_exclusion_count(self, value: int):
        self._set_val("exclusion_count", max(0, value))
        self._record("set_exclusion_count", {"value": value})

    def set_cumulative_uncertainty(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("cumulative_uncertainty", max(0.0, value))
        self._record("set_cumulative_uncertainty", {"value": value})

    def increment_records(self, n: int = 1):
        self._set_val("total_records_processed", self._get_val("total_records_processed") + n)
        self._record("increment_records", {"n": n})

    def set_cumulative_density(self, value: float):
        if math.isnan(value) or math.isinf(value):
            return
        self._set_val("cumulative_density", max(0.0, value))
        self._record("set_cumulative_density", {"value": value})

    def accumulate_density(self, delta: float):
        self._set_val("cumulative_density", max(0.0, self._get_val("cumulative_density") + delta))
        self._record("accumulate_density", {"delta": delta})

    @property
    def schema_instability(self):
        return dict(self._get_val("_schema_instability"))

    # ─── Controlled Mutations — Schema Instability ───────────────────────

    def get_schema_instability(self, role: str) -> float:
        return self._get_val("_schema_instability").get(role, 0.5)

    def set_schema_instability(self, role: str, value: float):
        inst = self._get_val("_schema_instability")
        inst[role] = max(0.0, min(1.0, value))
        self._set_val("_schema_instability", inst)
        self._record("set_schema_instability", {"role": role, "value": value})

    # ─── Bulk/Derived Setters ────────────────────────────────────────────

    def update_from_regions(self, regions, region_count: Optional[int] = None):
        if not regions:
            return
        n = region_count if region_count else len(regions)
        if n <= 0:
            return
        avg_convergence = sum(r.local_convergence for r in regions) / n
        avg_temp = sum(getattr(r, 'local_temperature', 0.5) for r in regions) / n
        avg_energy = sum(r.local_energy for r in regions) / n
        avg_instability = sum(r.instability for r in regions) / n
        
        self.set_convergence(avg_convergence)
        self.set_temperature(avg_temp)
        self.set_energy(avg_energy)
        self.set_entropy(avg_instability)
        self._set_val("cumulative_uncertainty", sum(r.instability for r in regions))

    def evolve_from_regions(self, regions, region_count: Optional[int] = None):
        if not regions:
            return
        n = region_count if region_count else len(regions)
        if n <= 0:
            return
        avg_convergence = sum(getattr(r, 'integrity', 0.5) for r in regions) / n
        avg_temp = sum(getattr(r, 'local_temperature', 0.5) for r in regions) / n
        avg_energy = sum(r.local_energy for r in regions) / n
        avg_instability = sum(r.instability for r in regions) / n
        
        # Phase 56/58: Entropy Economy — smooth entropy growth but ensure it settled to 0
        cur_entropy = self._get_val("global_entropy")
        # Faster decay (0.5 weight) than growth (0.3 weight in previous iterations)
        # to ensure stabilization is responsive.
        self._set_val("global_entropy", cur_entropy * 0.5 + avg_instability * 0.5)
        
        self._set_val("_convergence", avg_convergence)
        self._set_val("_temperature", avg_temp)
        # Update smoothed metrics (EMA-style)
        prev_s = self._get_val("_smoothed_structural")
        self._set_val("_smoothed_structural", prev_s * 0.9 + avg_instability * 0.1)
        prev_r = self._get_val("_smoothed_runtime")
        self._set_val("_smoothed_runtime", prev_r * 0.9 + avg_temp * 0.1)
        attractor_strength = 1.0 / (1.0 + 2.718 ** (-15 * (avg_convergence - 0.6)))
        attractor_pull = min(attractor_strength * avg_convergence * 2.0, 2.0)
        target_energy = max(0.0, avg_energy - attractor_pull)
        cur_energy = self._get_val("global_energy")
        self._set_val("global_energy", cur_energy * 0.8 + target_energy * 0.2)

    def from_dict(self, data: dict):
        self.clear()
        self._set_val("global_energy", data.get("global_energy", 5.0))
        self._set_val("global_entropy", data.get("global_entropy", 0.5))
        self._set_val("exclusion_count", data.get("exclusion_count", 0))
        self._set_val("total_records_processed", data.get("total_records_processed", 0))
        self._set_val("cumulative_density", data.get("cumulative_density", 0.0))
        self._set_val("cumulative_uncertainty", data.get("cumulative_uncertainty", 0.0))
        self._set_val("dataset_coherence", data.get("dataset_coherence", 0.5))
        self._set_val("_convergence", data.get("_convergence", 0.5))
        self._set_val("_temperature", data.get("_temperature", 0.5))
        self._set_val("_integrity", data.get("_integrity", 0.5))
        self._set_val("_smoothed_structural", data.get("_smoothed_structural", 0.4))
        self._set_val("_smoothed_runtime", data.get("_smoothed_runtime", 0.3))
        self._set_val("_smoothed_temperature", data.get("_smoothed_temperature", 0.5))
        self._set_val("stability_debt", data.get("stability_debt", 0.0))
        self._set_val("_schema_instability", dict(data.get("schema_instability", {})))

    def to_dict(self) -> dict:
        return {
            "global_energy": self.global_energy,
            "global_entropy": self.global_entropy,
            "exclusion_count": self.exclusion_count,
            "total_records_processed": self.total_records_processed,
            "cumulative_density": self.cumulative_density,
            "cumulative_uncertainty": self.cumulative_uncertainty,
            "dataset_coherence": self.dataset_coherence,
            "_convergence": self.convergence,
            "_temperature": self.temperature,
            "_integrity": self.integrity,
            "_smoothed_structural": self._get_val("_smoothed_structural"),
            "_smoothed_runtime": self._get_val("_smoothed_runtime"),
            "_smoothed_temperature": self._get_val("_smoothed_temperature"),
            "stability_debt": self.stability_debt,
            "schema_instability": self.schema_instability,
        }

    def clear(self):
        self._set_val("global_energy", 5.0)
        self._set_val("global_entropy", 0.5)
        self._set_val("exclusion_count", 0)
        self._set_val("total_records_processed", 0)
        self._set_val("cumulative_density", 0.0)
        self._set_val("cumulative_uncertainty", 0.0)
        self._set_val("dataset_coherence", 0.5)
        self._set_val("_convergence", 0.5)
        self._set_val("_temperature", 0.5)
        self._set_val("_integrity", 0.5)
        self._set_val("_smoothed_structural", 0.4)
        self._set_val("_smoothed_runtime", 0.3)
        self._set_val("_smoothed_temperature", 0.5)
        self._set_val("stability_debt", 0.0)
        self._set_val("_schema_instability", {})

    def merge(self, other_data: dict, alpha: float = 0.5):
        """Merge remote energy state into local (Phase 32)."""
        
        def merge_field(field: str, remote_val: float, mode: str = "avg"):
            # All internal keys in EnergyState use underscores
            k = field if field.startswith("_") else f"_{field}"
            local_val = self._get_val(k)
            
            if mode == "avg":
                new_val = local_val * (1.0 - alpha) + remote_val * alpha
            elif mode == "max":
                new_val = max(local_val, remote_val)
            
            self._set_val(k, new_val)

        merge_field("global_energy", other_data.get("global_energy", 5.0))
        merge_field("global_entropy", other_data.get("global_entropy", 0.5))
        merge_field("exclusion_count", other_data.get("exclusion_count", 0), mode="max")
        merge_field("total_records_processed", other_data.get("total_records_processed", 0), mode="max")
        merge_field("cumulative_density", other_data.get("cumulative_density", 0.0))
        merge_field("cumulative_uncertainty", other_data.get("cumulative_uncertainty", 0.0))
        merge_field("dataset_coherence", other_data.get("dataset_coherence", 0.5))
        
        # Merge derived metrics
        merge_field("_convergence", other_data.get("_convergence", 0.5))
        merge_field("_temperature", other_data.get("_temperature", 0.5))
        merge_field("_integrity", other_data.get("_integrity", 0.5))
        merge_field("stability_debt", other_data.get("stability_debt", 0.0))
        merge_field("_smoothed_structural", other_data.get("_smoothed_structural", 0.4))
        merge_field("_smoothed_runtime", other_data.get("_smoothed_runtime", 0.3))
        merge_field("_smoothed_temperature", other_data.get("_smoothed_temperature", 0.5))

        # Merge schema instability
        remote_inst = other_data.get("schema_instability", {})
        for role, r_val in remote_inst.items():
            l_val = self.get_schema_instability(role)
            self.set_schema_instability(role, l_val * (1.0 - alpha) + r_val * alpha)
        
        self._record("merge", {"alpha": alpha})

