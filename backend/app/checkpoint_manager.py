import json
import logging
import time
from pathlib import Path
from typing import List, Optional


def get_world_state():
    import app.semantic_world_state

    return app.semantic_world_state.get_world_state()


class CheckpointManager:
    """Manages persistent, versioned snapshots of the entire world state."""

    def __init__(self, base_dir: str = "checkpoints"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(self, label: str = "auto") -> str:
        """Save a new versioned checkpoint of the current world state."""
        ws = get_world_state()
        state_dict = ws.to_dict()

        timestamp = int(time.time())
        filename = f"checkpoint_{label}_{timestamp}.json"
        filepath = self.base_dir / filename

        try:
            with open(filepath, "w") as f:
                json.dump(state_dict, f, indent=2)
            logging.getLogger(__name__).info(f"Created checkpoint: {filename}")
            return str(filepath)
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to create checkpoint: {e}")
            raise

    def load_checkpoint(self, filepath: str):
        """Restore world state from a checkpoint file."""
        try:
            with open(filepath, "r") as f:
                state_dict = json.load(f)
            get_world_state().from_dict(state_dict)
            logging.getLogger(__name__).info(f"Restored from checkpoint: {filepath}")
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to load checkpoint: {e}")
            raise

    def list_checkpoints(self) -> List[dict]:
        """List all available checkpoints."""
        checkpoints = []
        for f in self.base_dir.glob("checkpoint_*.json"):
            checkpoints.append({"filename": f.name, "path": str(f), "mtime": f.stat().st_mtime})
        return sorted(checkpoints, key=lambda x: x["mtime"], reverse=True)

    def get_latest_checkpoint(self) -> Optional[str]:
        """Return the path to the most recent checkpoint."""
        list_cp = self.list_checkpoints()
        return list_cp[0]["path"] if list_cp else None


_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    global _manager
    if _manager is None:
        # Resolve path relative to backend root
        base = Path(__file__).parent.parent / "data" / "checkpoints"
        _manager = CheckpointManager(str(base))
    return _manager
