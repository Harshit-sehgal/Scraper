"""Simple JSON persistence for job and recycle-bin state with safety guarantees.

Storage safety features:
- Atomic writes via temp-file + rename (no partial writes)
- Automatic backup before overwrite
- Integrity validation on load with fallback to backup
- Background thread serialization (non-blocking saves)
- Reasonable retry for transient I/O errors
"""

import datetime
import json
import logging
import os
import shutil
from pathlib import Path
from threading import Lock
import concurrent.futures

from typing import Optional

from app.models import Job, JobStatus

_STATE_LOCK = Lock()
_SAVE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"

# Keep the last backup to survive corrupt writes
_BACKUP_SUFFIX = ".bak"
_SAVE_RETRIES = 3


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


def get_state_file_path() -> Path:
    env_path = os.getenv("DATAFORGE_STATE_FILE", "").strip()
    if env_path:
        return Path(env_path).expanduser()

    from app.config import settings
    if settings.STATE_FILE_PATH:
        return Path(settings.STATE_FILE_PATH).expanduser()
    return _DEFAULT_STATE_FILE


def _validate_payload(payload: dict) -> bool:
    """Basic structural validation of the loaded state payload."""
    if not isinstance(payload, dict):
        return False
    if "jobs" in payload and not isinstance(payload["jobs"], list):
        return False
    if "recycle_bin" in payload and not isinstance(payload["recycle_bin"], list):
        return False
    return True


def _try_load_from(path: Path) -> Optional[dict]:
    """Try to load and parse the JSON state file. Returns None on failure."""
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if _validate_payload(payload):
            return payload
        logging.error("State file %s failed structural validation", path)
    except Exception as e:
        logging.error("Failed to read/parse state file %s: %s", path, e)
    return None


def load_state() -> tuple[dict[str, Job], dict[str, Job], Optional[dict]]:
    path = get_state_file_path()
    if not path.exists():
        return {}, {}, None

    backup_path = path.with_suffix(path.suffix + _BACKUP_SUFFIX)

    # Try primary file first
    payload = _try_load_from(path)

    # Fall back to backup if primary is corrupt
    if payload is None and backup_path.exists():
        logging.warning("Primary state file corrupt, falling back to backup: %s", backup_path)
        payload = _try_load_from(backup_path)

    # Still nothing — return empty state
    if payload is None:
        logging.error("All state file sources failed; returning empty state")
        return {}, {}, None

    jobs_store: dict[str, Job] = {}
    recycle_bin_store: dict[str, Job] = {}

    for raw in payload.get("jobs", []):
        try:
            job = Job.model_validate(raw)
            jobs_store[job.id] = job
        except Exception as e:
            logging.exception("Skipping invalid job entry: %s", e)

    for raw in payload.get("recycle_bin", []):
        try:
            job = Job.model_validate(raw)
            recycle_bin_store[job.id] = job
        except Exception as e:
            logging.exception("Skipping invalid recycle-bin entry: %s", e)

    # Jobs that were in-progress during shutdown are marked failed on recovery.
    for job in jobs_store.values():
        if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
            job.status = JobStatus.FAILED
            job.error = "Recovered after restart while still in progress."
            job.completed_at = _now_iso()
            job.cancel_requested = False

    # Phase 68: Semantic field state — restore from persisted world_state if present
    world_state_data: Optional[dict] = payload.get("world_state")

    return jobs_store, recycle_bin_store, world_state_data


def _write_state_to_disk(path: Path, payload: dict) -> None:
    """Atomically write state to disk with retry and backup creation."""
    temp_path = path.with_suffix(path.suffix + ".tmp")
    backup_path = path.with_suffix(path.suffix + _BACKUP_SUFFIX)

    for attempt in range(1, _SAVE_RETRIES + 1):
        try:
            with _STATE_LOCK:
                # Create backup before overwriting if the file already exists
                if path.exists() and not backup_path.exists():
                    shutil.copy2(path, backup_path)
                elif path.exists():
                    # Rotate: keep one backup generation
                    older_backup = path.with_suffix(path.suffix + ".bak.old")
                    if backup_path.exists():
                        shutil.move(str(backup_path), str(older_backup))
                    shutil.copy2(path, backup_path)

                temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                temp_path.replace(path)
                # Success — clean up old backups
                old_backup = path.with_suffix(path.suffix + ".bak.old")
                if old_backup.exists():
                    old_backup.unlink(missing_ok=True)
                return
        except Exception as e:
            if attempt < _SAVE_RETRIES:
                logging.warning(
                    "State save attempt %d/%d failed for %s: %s",
                    attempt, _SAVE_RETRIES, path, e,
                )
            else:
                logging.exception(
                    "Failed to persist state after %d attempts to %s: %s",
                    _SAVE_RETRIES, path, e,
                )


def save_state(jobs_store: dict[str, Job], recycle_bin_store: dict[str, Job]) -> None:
    path = get_state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Phase 68: Persist semantic field state alongside jobs
    world_state_data = None
    try:
        from app.semantic_world_state import get_world_state
        ws = get_world_state()
        world_state_data = ws.to_dict()
    except Exception as e:
        logging.exception("Failed to serialize semantic world state: %s", e)

    payload = {
        "saved_at": _now_iso(),
        "jobs": [job.model_dump() for job in jobs_store.values()],
        "recycle_bin": [job.model_dump() for job in recycle_bin_store.values()],
        "world_state": world_state_data,
    }

    _SAVE_EXECUTOR.submit(_write_state_to_disk, path, payload)


def flush_state_writes():
    """Wait for all pending background state writes to complete.

    Should be called during graceful shutdown to ensure no state is lost.
    This is a synchronous call that blocks until all pending writes finish.
    """
    global _SAVE_EXECUTOR
    _SAVE_EXECUTOR.shutdown(wait=True)
    # Recreate executor for any future writes
    _SAVE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)
