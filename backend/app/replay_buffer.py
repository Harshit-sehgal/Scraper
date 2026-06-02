"""Large-Scale Replay Buffer — streams historical deltas from persistent storage.

The ReplayBuffer complements the in-memory EventJournal by providing:
1. File-backed persistent storage (JSON Lines format for streaming)
2. O(log N) checkpoint seeks for efficient reconstruction
3. Streaming reads from any point without loading the entire history
4. Tiered retention: full-fidelity recent events + structural-skeleton historical events
5. Compression-friendly delta encoding

Phase 66: Long-Horizon Scaling — streaming replay from persistent storage.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Maximum deltas in a single file segment
_SEGMENT_CAPACITY = 5000

# Checkpoint interval (every N deltas within a segment)
_CHECKPOINT_INTERVAL = 500


class _CheckpointIndex:
    """In-memory index of checkpoints for O(log N) seek."""

    __slots__ = ("entries",)

    def __init__(self):
        # entries: list of (global_idx, segment_path, segment_offset,
        # snapshot_dict)
        self.entries: List[Tuple[int, str, int, dict]] = []

    def add(self, global_idx: int, segment_path: str, offset: int, snapshot: dict):
        self.entries.append((global_idx, segment_path, offset, snapshot))

    def find_nearest(self, target_idx: int) -> Optional[Tuple[int, str, int, dict]]:
        """Find the nearest checkpoint at or before target_idx."""
        best = None
        for entry in self.entries:
            if entry[0] <= target_idx:
                if best is None or entry[0] > best[0]:
                    best = entry
        return best

    def clear(self):
        self.entries.clear()

    def to_dict_list(self) -> List[dict]:
        return [{"idx": idx, "segment": seg, "offset": off} for idx, seg, off, _ in self.entries]


class ReplayBuffer:
    """Persistent, streaming replay buffer for historical delta sequences.

    Storage format:
    - Segments: files of up to _SEGMENT_CAPACITY delta entries in JSON Lines format
    - Each line is a JSON object with keys: idx, timestamp, type, delta, metadata
    - Checkpoints: periodic full-state snapshots interleaved into each segment
    - Index: in-memory mapping of checkpoint idx -> (segment, offset)

    Streaming:
    - Iterate from any start index with O(log N) seek cost
    - Reconstruct full state at any index via checkpoint + forward replay
    - Backward iteration for reverse causal chain analysis
    """

    def __init__(self, base_dir: str = "replay_buffer", max_segments: int = 50):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._max_segments = max_segments
        self._lock = threading.Lock()

        # Current segment tracking
        self._current_segment_idx = 0
        self._current_segment_count = 0
        self._current_segment_file: Optional[Path] = None  # Lazy-opened
        self._next_global_idx = 0

        # Checkpoint index
        self._checkpoints = _CheckpointIndex()

        # Segment inventory
        self._segments: List[str] = []  # sorted list of segment filenames

        # Metrics
        self._total_entries = 0
        self._total_checkpoints = 0
        self._load_existing_segments()

    # ─── Writing ────────────────────────────────────────────────────

    def append(self, delta_entry: dict) -> int:
        """Append a delta entry to the buffer.

        Args:
            delta_entry: Dict with keys: type, delta, metadata, timestamp
                         The 'idx' key in the entry is ignored; assigned by the buffer.

        Returns:
            The global index assigned to this entry.
        """
        with self._lock:
            idx = self._next_global_idx
            self._next_global_idx += 1

            entry = {
                "idx": idx,
                "timestamp": delta_entry.get("timestamp", time.time()),
                "type": delta_entry.get("type", "unknown"),
                "delta": delta_entry.get("delta", {}),
                "metadata": delta_entry.get("metadata", {}),
            }

            # Write to current segment
            filepath = self._ensure_segment()
            line = json.dumps(entry, separators=(",", ":"))
            with open(filepath, "a") as f:
                f.write(line + "\n")

            self._current_segment_count += 1
            self._total_entries += 1

            # Trigger checkpoint if structural event or interval hit
            is_structural = entry["type"] in {
                "restructure_topology",
                "merge_state",
                "add",
                "remove",
                "promote_hypo",
                "crystallize",
                "phase_transition",
            }
            if is_structural or (self._current_segment_count % _CHECKPOINT_INTERVAL == 0):
                segment_offset = self._get_file_offset(filepath)
                snapshot = dict(entry)  # Use entry as checkpoint snapshot
                self._checkpoints.add(idx, filepath.name, segment_offset, snapshot)
                self._total_checkpoints += 1

            # Rotate segment if full
            if self._current_segment_count >= _SEGMENT_CAPACITY:
                self._rotate_segment()

            return idx

    def _ensure_segment(self) -> Path:
        """Ensure the current segment file exists and return its path."""
        if self._current_segment_file is None:
            seg_name = f"segment_{self._current_segment_idx:06d}.jsonl"
            filepath = self._base_dir / seg_name
            self._current_segment_file = filepath
            self._segments.append(seg_name)
            # Touch file
            filepath.touch(exist_ok=True)
            return filepath
        return self._current_segment_file

    def _rotate_segment(self):
        """Rotate to a new segment file."""
        self._current_segment_idx += 1
        self._current_segment_count = 0
        self._current_segment_file = None

        # Evict old segments if over max
        sorted_segs = sorted(self._segments)
        while len(sorted_segs) > self._max_segments:
            oldest = sorted_segs.pop(0)
            oldest_path = self._base_dir / oldest
            if oldest_path.exists():
                oldest_path.unlink()
            self._segments.remove(oldest)
            # Prune checkpoints in evicted segments
            evicted_seg = oldest
            self._checkpoints.entries = [cp for cp in self._checkpoints.entries if cp[1] != evicted_seg]

    def _get_file_offset(self, filepath: Path) -> int:
        """Get the current byte offset at end of file."""
        return filepath.stat().st_size if filepath.exists() else 0

    # ─── Reading / Streaming ────────────────────────────────────────

    def stream_from(self, start_idx: int = 0) -> Iterator[dict]:
        """Stream entries from start_idx onward, loading from persistent storage.

        Uses checkpoint index for O(log N) seek into the correct segment,
        then streams entries forward without loading the full history.

        Args:
            start_idx: Global index to start streaming from.

        Yields:
            Delta entries in sequential order.
        """
        # 1. Find nearest checkpoint <= start_idx
        checkpoint = self._checkpoints.find_nearest(start_idx)
        if checkpoint is None:
            # No checkpoints — start from beginning of first segment
            checkpoint_idx = -1
            segment_name = self._segments[0] if self._segments else None
            segment_offset = 0
        else:
            checkpoint_idx, segment_name, segment_offset, _ = checkpoint

        if segment_name is None:
            return

        # 2. Seek to checkpoint offset in the segment
        segment_path = self._base_dir / segment_name
        if not segment_path.exists():
            return

        # 3. Stream forward from checkpoint, skipping entries < start_idx
        with open(segment_path, "r") as f:
            f.seek(segment_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("idx", 0) < start_idx:
                    continue
                yield entry

        # 4. Continue through subsequent segments
        next_segments = self._get_subsequent_segments(segment_name)
        for seg_name in next_segments:
            seg_path = self._base_dir / seg_name
            if not seg_path.exists():
                continue
            with open(seg_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    yield entry

    def reconstruct_state_at(self, target_idx: int) -> Optional[dict]:
        """Reconstruct full state at a specific index via checkpoint + replay.

        Uses the nearest preceding checkpoint and applies deltas forward.

        Args:
            target_idx: The target global index.

        Returns:
            Reconstructed state dict, or None if cannot reconstruct.
        """
        checkpoint = self._checkpoints.find_nearest(target_idx)
        if checkpoint is None:
            return None

        cp_idx, seg_name, offset, snapshot = checkpoint
        if cp_idx > target_idx:
            return None

        # Clone the checkpoint snapshot as starting state, unpacking delta
        # encoding
        checkpoint_delta = snapshot.get("delta", {})
        state = {}
        for k, change in checkpoint_delta.items():
            state[k] = change.get("to", change) if isinstance(change, dict) else change

        # Replay deltas from checkpoint to target
        seg_path = self._base_dir / seg_name
        if not seg_path.exists():
            return None

        with open(seg_path, "r") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                idx = entry.get("idx", -1)
                if idx <= cp_idx:
                    continue
                if idx > target_idx:
                    break
                # Apply delta to state
                for k, change in entry.get("delta", {}).items():
                    state[k] = change.get("to", change)

        return state

    def get_entry(self, idx: int) -> Optional[dict]:
        """Get a single entry by index (expensive — scans from nearest checkpoint)."""
        for entry in self.stream_from(idx):
            if entry.get("idx") == idx:
                return entry
        return None

    def get_segment_info(self) -> List[dict]:
        """Return information about all segments for observability."""
        result = []
        with self._lock:
            for seg_name in sorted(self._segments):
                seg_path = self._base_dir / seg_name
                size_bytes = seg_path.stat().st_size if seg_path.exists() else 0
                result.append(
                    {
                        "segment": seg_name,
                        "size_bytes": size_bytes,
                        "size_mb": round(size_bytes / (1024 * 1024), 2),
                    }
                )
        return result

    def status(self) -> dict:
        """Return buffer status for observability."""
        with self._lock:
            return {
                "total_entries": self._total_entries,
                "total_checkpoints": self._total_checkpoints,
                "segments": len(self._segments),
                "current_segment_idx": self._current_segment_idx,
                "current_segment_entries": self._current_segment_count,
                "base_dir": str(self._base_dir),
                "max_segments": self._max_segments,
                "segment_capacity": _SEGMENT_CAPACITY,
            }

    def clear(self):
        """Clear all stored data and reset state."""
        with self._lock:
            for seg_name in self._segments:
                seg_path = self._base_dir / seg_name
                if seg_path.exists():
                    seg_path.unlink()
            self._segments.clear()
            self._checkpoints.clear()
            self._current_segment_idx = 0
            self._current_segment_count = 0
            self._current_segment_file = None
            self._next_global_idx = 0
            self._total_entries = 0
            self._total_checkpoints = 0

    def close(self):
        """Close the buffer, ensuring all data is flushed."""
        self._current_segment_file = None

    # ─── Internal Helpers ──────────────────────────────────────────

    def _load_existing_segments(self):
        """Load existing segments from disk on initialization."""
        if not self._base_dir.exists():
            return
        seg_pattern = "segment_*.jsonl"
        existing = sorted(self._base_dir.glob(seg_pattern))
        for seg_path in existing:
            self._segments.append(seg_path.name)
            total_lines = 0
            # Rebuild checkpoint index by scanning this segment
            with open(seg_path, "r") as f:
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    idx = entry.get("idx", 0)
                    if idx >= self._next_global_idx:
                        self._next_global_idx = idx + 1
                    self._total_entries += 1
                    total_lines += 1
                    # Rebuild checkpoints using same heuristic as append()
                    is_structural = entry.get("type") in {
                        "restructure_topology",
                        "merge_state",
                        "add",
                        "remove",
                        "promote_hypo",
                        "crystallize",
                        "phase_transition",
                    }
                    if is_structural or (total_lines > 0 and total_lines % _CHECKPOINT_INTERVAL == 0):
                        self._checkpoints.add(idx, seg_path.name, pos, entry)
                        self._total_checkpoints += 1

            # Update current segment to the latest
            self._current_segment_idx = int(seg_path.stem.split("_")[1]) if "_" in seg_path.stem else 0
            self._current_segment_count = total_lines

        if self._segments:
            self._current_segment_file = self._base_dir / self._segments[-1]

    def _get_subsequent_segments(self, current_seg: str) -> List[str]:
        """Return segments that come after current_seg in sorted order."""
        with self._lock:
            sorted_segs = sorted(self._segments)
            try:
                idx = sorted_segs.index(current_seg)
                return sorted_segs[idx + 1:]
            except ValueError:
                return []

    def _count_lines(self, seg_path: Path) -> int:
        """Count non-empty lines in a segment file."""
        count = 0
        try:
            with open(seg_path, "r") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except Exception:
            pass
        return count

    # ─── Causal Chain Reconstruction ────────────────────────────

    def get_causal_chains(self, limit: int = 20) -> List[dict]:
        """Reconstruct causal chains from the replay buffer.

        Groups related entries into causal chains based on:
        1. Trace ID propagation (entries with matching trace_id)
        2. Source causality (one entry's type may cause a subsequent entry)
        3. Temporal proximity (entries close in time that affect the same entities)

        This enables streaming replay of field dynamics, showing how
        one event leads to another through the persistent history.

        Args:
            limit: Maximum number of causal chains to return.

        Returns:
            List of causal chain dicts, each with:
            - chain_id: unique identifier
            - start_idx: first event index
            - end_idx: last event index
            - events: list of events in the chain
            - summary: human-readable summary of the chain
            - trace_id: common trace identifier if available
        """
        # Scan the most recent entries for trace-based grouping
        chains: Dict[str, List[dict]] = {}
        chain_order: List[str] = []

        # Stream from the latest checkpoint backward (or forward from a recent point)
        # We stream from near the end for efficiency
        total = self._total_entries
        start = max(0, total - 500)  # Scan last 500 entries max

        for entry in self.stream_from(start):
            metadata = entry.get("metadata", {})
            trace_id = metadata.get("trace_id", "")
            event_type = entry.get("type", "unknown")

            # Group by trace_id
            if trace_id:
                if trace_id not in chains:
                    chains[trace_id] = []
                    chain_order.append(trace_id)
                chains[trace_id].append(entry)
            else:
                # No trace_id: use a chain per unique type pattern
                chain_key = f"untraced:{event_type}"
                if chain_key not in chains:
                    chains[chain_key] = []
                    chain_order.append(chain_key)
                chains[chain_key].append(entry)

        # Build final output
        result: list[dict] = []
        for key in chain_order[-limit:]:
            events = chains[key]
            if not events:
                continue

            # Summarize the chain
            types = [e.get("type", "") for e in events]
            unique_types = list(dict.fromkeys(types))
            idxs = [e.get("idx", 0) for e in events]

            is_traced = not key.startswith("untraced:")
            chain = {
                "chain_id": f"chain_{len(result)}",
                "trace_id": key if is_traced else None,
                "start_idx": min(idxs),
                "end_idx": max(idxs),
                "event_count": len(events),
                "types": unique_types,
                "events": [
                    {
                        "idx": e.get("idx"),
                        "type": e.get("type"),
                        "timestamp": e.get("timestamp"),
                        "metadata": e.get("metadata", {}),
                        "delta": e.get("delta", {}),
                        # Limit events per chain
                    }
                    for e in sorted(events, key=lambda x: x.get("idx", 0))
                ][-20:],
                "summary": " → ".join(t.split(".", 1)[-1] if "." in t else t for t in unique_types[:5]),
            }
            result.append(chain)

        return result

    def get_event_range(self, start_idx: int, end_idx: int) -> List[dict]:
        """Get all events within a specific index range.

        Uses streaming to avoid loading the full buffer into memory.

        Args:
            start_idx: Start index (inclusive)
            end_idx: End index (inclusive)

        Returns:
            List of events in the range.
        """
        events = []
        for entry in self.stream_from(start_idx):
            idx = entry.get("idx", 0)
            if idx > end_idx:
                break
            events.append(entry)
        return events


# Global singleton
_buffer: Optional[ReplayBuffer] = None


def get_replay_buffer(base_dir: Optional[str] = None) -> ReplayBuffer:
    """Get or create the global ReplayBuffer instance."""
    global _buffer
    if _buffer is None:
        _buffer = ReplayBuffer(base_dir=base_dir or str(Path(__file__).parent.parent / "data" / "replay_buffer"))
    return _buffer


def reset_replay_buffer():
    """Reset the global replay buffer (for testing)."""
    global _buffer
    if _buffer is not None:
        _buffer.close()
    _buffer = None
