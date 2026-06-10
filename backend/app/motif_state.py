from typing import Any

"""MotifState — owns all motif memory and stability tracking.

True ownership boundary: NO external code should mutate motif_counts,
motif_timestamps, or motif_stability directly. All changes go through
this state object which enforces decay and pruning invariants.

Owns:
- motif_counts: Counter[Tuple[str, ...]] — recurrence counts per motif
- motif_timestamps: Dict[Tuple[str, ...], int] — record index of last reinforcement
- motif_stability: Dict[Tuple[str, ...], float] — temporal stability score
"""

import logging
import math
from collections import Counter
from collections.abc import Callable

from app.transaction_context import active_transaction

logger = logging.getLogger(__name__)


class MotifState:
    """Sole owner of the semantic field's motif structures."""

    def __init__(self, delta_callback: Callable[[str, str, dict], None] | None = None) -> None:
        self._delta_callback = delta_callback
        self._motif_counts: Counter = Counter()
        self._motif_timestamps: dict[tuple[str, ...], int] = {}
        self._motif_stability: dict[tuple[str, ...], float] = {}

    @property
    def _staging(self) -> dict | None:
        tx = active_transaction.get()
        if tx is not None:
            return tx.get(f"motif_staging_{id(self)}")
        return None

    @_staging.setter
    def _staging(self, value: dict | None) -> None:
        tx = active_transaction.get()
        if tx is not None:
            tx[f"motif_staging_{id(self)}"] = value

    def _record(self, action: str, details: dict[str, Any]) -> None:
        if self._delta_callback:
            self._delta_callback("motif", action, details)

    # ─── Transaction Support ─────────────────────────────────────────────

    def begin_transaction(self) -> None:
        """Snapshot current state for staging."""
        self._staging = {
            "motif_counts": Counter(self._motif_counts),
            "motif_timestamps": dict(self._motif_timestamps),
            "motif_stability": dict(self._motif_stability),
        }

    def commit(self) -> None:
        """Apply staged changes."""
        if self._staging is not None:
            self._motif_counts = self._staging["motif_counts"]
            self._motif_timestamps = self._staging["motif_timestamps"]
            self._motif_stability = self._staging["motif_stability"]
            self._staging = None

    def rollback(self) -> None:
        self._staging = None

    def _get_struct(self, key: str):
        if self._staging is not None:
            return self._staging[key]
        attr_map = {
            "motif_counts": "_motif_counts",
            "motif_timestamps": "_motif_timestamps",
            "motif_stability": "_motif_stability",
        }
        return getattr(self, attr_map[key])

    def _set_struct(self, key: str, val) -> None:
        if self._staging is not None:
            self._staging[key] = val
        else:
            attr_map = {
                "motif_counts": "_motif_counts",
                "motif_timestamps": "_motif_timestamps",
                "motif_stability": "_motif_stability",
            }
            setattr(self, attr_map[key], val)

    # ─── Read-Only Accessors ─────────────────────────────────────────────

    @property
    def motif_counts(self) -> Counter:
        return Counter(self._get_struct("motif_counts"))

    @property
    def motif_timestamps(self) -> dict[tuple[str, ...], int]:
        return dict(self._get_struct("motif_timestamps"))

    @property
    def motif_stability(self) -> dict[tuple[str, ...], float]:
        return dict(self._get_struct("motif_stability"))

    def get_count(self, motif: tuple[str, ...]) -> int:
        return self._get_struct("motif_counts").get(motif, 0)  # type: ignore[no-any-return]

    def get_timestamp(self, motif: tuple[str, ...]) -> int:
        return self._get_struct("motif_timestamps").get(motif, 0)  # type: ignore[no-any-return]

    def get_stability(self, motif: tuple[str, ...]) -> float:
        return self._get_struct("motif_stability").get(motif, 0.0)  # type: ignore[no-any-return]

    def count(self) -> int:
        return len(self._get_struct("motif_counts"))

    # ─── Controlled Mutations ───────────────────────────────────────────

    def reinforce(self, motif: tuple[str, ...], current_record: int) -> None:
        """Reinforce a structural motif with temporal awareness."""
        counts = self._get_struct("motif_counts")
        counts[motif] += 1
        self._set_struct("motif_counts", counts)

        times = self._get_struct("motif_timestamps")
        times[motif] = current_record
        self._set_struct("motif_timestamps", times)

        stabs = self._get_struct("motif_stability")
        stabs[motif] = self.compute_stability(motif, current_record)
        self._set_struct("motif_stability", stabs)
        self._record("reinforce", {"motif": motif, "current_record": current_record})

    def compute_stability(self, motif: tuple[str, ...], total_records: int) -> float:
        """Compute temporal stability score for a motif (0 - 1)."""
        if total_records == 0:
            return 0.0
        counts = self._get_struct("motif_counts")
        times = self._get_struct("motif_timestamps")
        count = counts.get(motif, 0)
        last_seen = times.get(motif, 0)
        age = total_records - last_seen
        decay_factor = math.exp(-age / 2000.0)
        base_stability = count / max(total_records, 1)
        return min(base_stability * decay_factor, 1.0)  # type: ignore[no-any-return]

    def prune_weak(self, threshold: float = 0.05) -> None:
        """Remove motifs that have decayed below threshold."""
        stabs = self._get_struct("motif_stability")
        counts = self._get_struct("motif_counts")
        times = self._get_struct("motif_timestamps")
        for motif in list(stabs.keys()):
            if stabs[motif] < threshold:
                del stabs[motif]
                counts.pop(motif, None)
                times.pop(motif, None)
        self._set_struct("motif_stability", stabs)
        self._set_struct("motif_counts", counts)
        self._set_struct("motif_timestamps", times)

    def prune_aged(self, max_stability: float = 0.01) -> None:
        """Remove motifs whose stability has decayed below max_stability."""
        stabs = self._get_struct("motif_stability")
        counts = self._get_struct("motif_counts")
        times = self._get_struct("motif_timestamps")
        for motif in list(counts.keys()):
            if motif in stabs and stabs[motif] < max_stability:
                del counts[motif]
                times.pop(motif, None)
                stabs.pop(motif, None)
        self._set_struct("motif_counts", counts)
        self._set_struct("motif_timestamps", times)
        self._set_struct("motif_stability", stabs)

    def remove(self, motif: tuple[str, ...]) -> None:
        """Remove a specific motif from all stores."""
        counts = self._get_struct("motif_counts")
        times = self._get_struct("motif_timestamps")
        stabs = self._get_struct("motif_stability")
        counts.pop(motif, None)
        times.pop(motif, None)
        stabs.pop(motif, None)
        self._set_struct("motif_counts", counts)
        self._set_struct("motif_timestamps", times)
        self._set_struct("motif_stability", stabs)

    def predict_future_motifs(self, current_record: int, threshold: float = 0.2) -> list[Any]:
        """Forecast future motifs based on recent growth and stability."""
        predictions = []
        counts = self._get_struct("motif_counts")
        stabs = self._get_struct("motif_stability")
        times = self._get_struct("motif_timestamps")
        for motif, count in counts.items():
            stability = stabs.get(motif, 0.0)
            last_seen = times.get(motif, 0)
            # Recency: 1.0 if seen this record, 0.0 if seen > 1000 records ago
            recency = max(0.0, 1.0 - (current_record - last_seen) / 1000.0)
            # Growth: count normalized by records, amplified by recency
            growth = (count / max(current_record, 1)) * (1.0 + recency * 2.0)
            if growth > threshold and stability < 0.4:  # Rising but not yet stable
                predictions.append(motif)
        return predictions

    # ─── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "motif_counts": {str(k): v for k, v in self._motif_counts.items()},
            "motif_timestamps": {str(k): v for k, v in self._motif_timestamps.items()},
            "motif_stability": {str(k): v for k, v in self._motif_stability.items()},
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self.clear()
        # Build the three target containers in local variables, then assign
        # them through ``_set_struct`` so the active transaction's staging
        # area is updated in lock-step (previously we wrote directly to
        # ``self._motif_counts[...]`` which bypassed the staging — a
        # in-flight transaction would never see the new keys and a
        # rollback would leave the in-memory state out of sync).
        counts: Counter = Counter()
        for k, v in data.get("motif_counts", {}).items():
            counts[tuple(self._parse_motif_key(k))] = v
        timestamps: dict[tuple[Any, ...], Any] = {}
        for k, v in data.get("motif_timestamps", {}).items():
            timestamps[tuple(self._parse_motif_key(k))] = v
        stability: dict[tuple[Any, ...], Any] = {}
        for k, v in data.get("motif_stability", {}).items():
            stability[tuple(self._parse_motif_key(k))] = v
        self._set_struct("motif_counts", counts)
        self._set_struct("motif_timestamps", timestamps)
        self._set_struct("motif_stability", stability)

    MAX_MOTIF_KEY_LENGTH = 1_000_000

    def _parse_motif_key(self, key: str) -> tuple[Any, ...]:
        import ast

        if len(key) > self.MAX_MOTIF_KEY_LENGTH:
            logger.warning("Motif key too long (%d chars), falling back to split", len(key))
            return tuple(key.split(", "))

        try:
            parsed = ast.literal_eval(key)  # nosec
            if isinstance(parsed, tuple):
                return parsed
        except (ValueError, SyntaxError):
            logger.debug("Fallback parsing motif key: %s", key)
        return tuple(key.split(", "))

    def clear(self) -> None:
        self._set_struct("motif_counts", Counter())
        self._set_struct("motif_timestamps", {})
        self._set_struct("motif_stability", {})

    def merge(self, other_data: dict[str, Any]) -> None:
        """Merge motif memory from another node or branch (Phase 32 / 39)."""
        counts = self._get_struct("motif_counts")
        times = self._get_struct("motif_timestamps")
        stabs = self._get_struct("motif_stability")

        remote_counts = other_data.get("motif_counts", {})
        for k_str, count in remote_counts.items():
            motif = self._parse_motif_key(k_str)
            counts[motif] = counts.get(motif, 0) + count
        self._set_struct("motif_counts", counts)

        remote_times = other_data.get("motif_timestamps", {})
        for k_str, ts in remote_times.items():
            motif = self._parse_motif_key(k_str)
            times[motif] = max(times.get(motif, 0), ts)
        self._set_struct("motif_timestamps", times)

        remote_stabs = other_data.get("motif_stability", {})
        for k_str, stab in remote_stabs.items():
            motif = self._parse_motif_key(k_str)
            stabs[motif] = max(stabs.get(motif, 0.0), stab)
        self._set_struct("motif_stability", stabs)

        self._record("merge", {"remote_motifs": len(remote_counts)})
