import json
import logging
import time
from pathlib import Path


def get_world_state():
    import app.semantic_world_state

    return app.semantic_world_state.get_world_state()


class CheckpointManager:
    """Manages persistent, versioned snapshots of the entire world state."""

    def __init__(self, base_dir: str = "checkpoints") -> None:
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
            with open(filepath, "w") as f:  # noqa: PTH123
                json.dump(state_dict, f, indent=2)
            logging.getLogger(__name__).info("Created checkpoint: %s", filename)
            return str(filepath)
        except Exception:
            logging.getLogger(__name__).exception("Failed to create checkpoint")
            raise

    def load_checkpoint(self, filepath: str) -> None:
        """Restore world state from a checkpoint file."""
        try:
            with open(filepath) as f:  # noqa: PTH123
                state_dict = json.load(f)
            get_world_state().from_dict(state_dict)
            logging.getLogger(__name__).info("Restored from checkpoint: %s", filepath)
        except Exception:
            logging.getLogger(__name__).exception("Failed to load checkpoint")
            raise

    def list_checkpoints(self) -> list[dict]:
        """List all available checkpoints."""
        checkpoints = []
        for f in self.base_dir.glob("checkpoint_*.json"):
            checkpoints.append({"filename": f.name, "path": str(f), "mtime": f.stat().st_mtime})
        return sorted(checkpoints, key=lambda x: x["mtime"], reverse=True)

    def get_latest_checkpoint(self) -> str | None:
        """Return the path to the most recent checkpoint."""
        list_cp = self.list_checkpoints()
        return list_cp[0]["path"] if list_cp else None


_manager: CheckpointManager | None = None


def get_checkpoint_manager() -> CheckpointManager:
    global _manager
    if _manager is None:
        # Resolve path relative to backend root
        base = Path(__file__).parent.parent / "data" / "checkpoints"
        _manager = CheckpointManager(str(base))
    return _manager
