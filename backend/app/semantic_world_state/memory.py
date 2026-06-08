# mypy: ignore-errors
# type: ignore  # noqa: PGH003

from app.invariant_firewall import requires_invariants


class MemoryMixin:
    @requires_invariants
    def reinforce_motif(self, motif: tuple[str, ...]) -> None:
        """Reinforce a structural motif with temporal awareness."""
        self._motif.reinforce(motif, self.metrics.total_records_processed)

    def get_motif_stability(self, motif: tuple[str, ...]) -> float:
        """Get temporal stability score for a motif (0 - 1)."""
        return self._motif.compute_stability(motif, self.metrics.total_records_processed)

    @requires_invariants
    def apply_memory_decay(self, rate: float = 0.01) -> None:
        """Globally decay old or weak semantic structures to reduce entropy.

        LAW 5: No fixed evolution cadence. Decay is triggered by field demand
        (entropy disorder or field pressure), not a procedural record counter.
        """
        # Field-demand trigger: decay when entropy is high (needs cleanup)
        # or when pressure is moderate (some tension to resolve).
        # Minimum context guard prevents firing on initialization defaults
        # (global_entropy starts at 0.5, above the 0.4 threshold).
        has_context = self.metrics.total_records_processed >= 5
        should_decay = has_context and (self.metrics.global_entropy > 0.4 or self.metrics.field_pressure > 0.3)
        if not should_decay:
            return
        self._manifold.decay_compatibilities(rate=rate)
        self._motif.prune_aged(max_stability=0.01)
