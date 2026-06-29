"""Simple JSON persistence for job and recycle-bin state with safety guarantees.

Storage safety features:
- Atomic writes via temp-file + rename (no partial writes)
- Automatic backup before overwrite
- Integrity validation on load with fallback to backup
- Background thread serialization (non-blocking saves)
- Reasonable retry for transient I / O errors
"""

import atexit
import concurrent.futures
import contextlib
import datetime
import errno  # Phase 73-HIGH: recoverable fsync codes
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any

from app.models import Job

logger = logging.getLogger(__name__)

_STATE_LOCK = Lock()
# L6: protect every access / mutation of the executor pointer. The
# previous code reassigned the module-level ``_SAVE_EXECUTOR`` without a
# guard, so a concurrent ``save_state()`` and ``flush_state_writes()``
# could (a) submit to the just-shutdown instance and lose the write, or
# (b) hand the caller a reference different from the one shutdown is
# operating on. Both halves now share a single lock.
_EXECUTOR_LOCK = Lock()
_SAVE_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None


def _ensure_save_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Return the live executor instance, allocating it on first use."""
    global _SAVE_EXECUTOR
    if _SAVE_EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _SAVE_EXECUTOR is None:
                _SAVE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="state_store_writer",
                )
    return _SAVE_EXECUTOR


def _get_or_build_save_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Get the current executor; if a prior shutdown left ``None``,
    allocate a fresh one so subsequent saves don't drop their writes.
    """
    global _SAVE_EXECUTOR
    current = _SAVE_EXECUTOR
    if current is not None:
        return current
    with _EXECUTOR_LOCK:
        if _SAVE_EXECUTOR is None:
            _SAVE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="state_store_writer",
            )
        return _SAVE_EXECUTOR


_DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"

# Keep the last backup to survive corrupt writes
_BACKUP_SUFFIX = ".bak"
_SAVE_RETRIES = 3


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def get_state_file_path() -> Path:
    from app.config import settings

    # Check settings.STATE_FILE first (dynamic @property that reads from
    # DATAFORGE_STATE_FILE env var), then fall back to STATE_FILE_PATH.
    if settings.STATE_FILE:
        return Path(settings.STATE_FILE).expanduser()

    if settings.STATE_FILE_PATH_DYNAMIC:
        return Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()

    return _DEFAULT_STATE_FILE


def _validate_payload(payload: dict[str, Any]) -> bool:
    """Basic structural validation of the loaded state payload."""
    if not isinstance(payload, dict):
        return False
    if "jobs" in payload and not isinstance(payload["jobs"], list):
        return False
    return not ("recycle_bin" in payload and not isinstance(payload["recycle_bin"], list))


def _try_load_from(path: Path) -> dict | None:
    """Try to load and parse the JSON state file. Returns None on failure."""
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if _validate_payload(payload):
            return payload  # type: ignore[no-any-return]
        logger.error("State file %s failed structural validation", path)
    except FileNotFoundError:
        logger.warning("State file not found: %s", path)
    except json.JSONDecodeError:
        logger.exception("State file %s contains invalid JSON", path)
    except PermissionError:
        logger.exception("Permission denied reading state file: %s", path)
    except OSError:
        logger.exception("OS error reading state file %s", path)
    return None


def load_state() -> tuple[dict[str, Job], dict[str, Job], dict | None]:
    path = get_state_file_path()
    if not path.exists():
        return {}, {}, None

    backup_path = path.with_suffix(path.suffix + _BACKUP_SUFFIX)

    # Try primary file first
    payload = _try_load_from(path)

    # Fall back to backup if primary is corrupt
    if payload is None and backup_path.exists():
        logger.warning("Primary state file corrupt, falling back to backup: %s", backup_path)
        payload = _try_load_from(backup_path)

    # Still nothing — return empty state
    if payload is None:
        logger.error("All state file sources failed; returning empty state")
        return {}, {}, None

    jobs_store: dict[str, Job] = {}
    recycle_bin_store: dict[str, Job] = {}

    for raw in payload.get("jobs", []):
        try:
            job = Job.model_validate(raw)
            jobs_store[job.id] = job
        except (ValueError, TypeError):
            logger.exception("Skipping invalid job entry during state load")

    for raw in payload.get("recycle_bin", []):
        try:
            job = Job.model_validate(raw)
            recycle_bin_store[job.id] = job
        except (ValueError, TypeError):
            logger.exception("Skipping invalid recycle-bin entry during state load")

    # Jobs that were in-progress during shutdown are marked failed on recovery.
    from app.services.job_state_machine import mark_recovered_failed

    for job in jobs_store.values():
        mark_recovered_failed(job)

    # Phase 68: Semantic field state — restore from persisted world_state if
    # present
    world_state_data: dict | None = payload.get("world_state")

    return jobs_store, recycle_bin_store, world_state_data


def _write_state_to_disk(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write state to disk with retry and backup creation."""
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

                # F-STATE-001: canonical atomic tempfile + fdopen
                # pattern.  ``write_text`` + re-opening with ``O_RDONLY``
                # is correct on Linux but fragile (TOCTOU between the
                # close and the re-open, and the second ``os.open`` is
                # not atomic with the write).  Use ``mkstemp`` to get an
                # exclusive fd we own through the fdopen, flush, fsync,
                # and ``os.replace`` sequence — matching every other
                # firing-squad module (semantic_persistence,
                # checkpoint_manager, domain_intelligence, etc.).
                fd, tmp_path = tempfile.mkstemp(
                    dir=str(path.parent),
                    suffix=path.suffix + ".tmp",
                    prefix=path.stem + ".",
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, str(path))
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp_path)
                    raise
                # Phase 73-HIGH: fsync the parent directory so the rename
                # entry is durable on disk. Without this, a crash between
                # ``replace`` and a subsequent clean shutdown can leave
                # the directory's inode flushed but the new ``path``
                # entry missing — meaning the old file is recovered on
                # restart, silently losing the latest snapshot. This is
                # the classical "lost rename" failure mode documented
                # in PostgreSQL, SQLite, and all crash-safe journaled
                # storage. We swallow ENOTSUP (e.g., some FUSE mounts)
                # and EROFS (read-only FS) because the rename itself
                # was successful and the data is durable on disk.
                try:
                    dir_fd = os.open(str(path.parent), os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except (OSError, AttributeError) as fsync_exc:
                    # ENOTSUP / EROFS are non-fatal: the data was
                    # persisted; only the directory entry durability is
                    # best-effort on those filesystems.
                    _err = getattr(fsync_exc, "errno", None)
                    if _err not in (None, getattr(errno, "ENOTSUP", -1), getattr(errno, "EROFS", -1)):
                        logger.warning("Parent-dir fsync failed for %s: %s", path.parent, fsync_exc)
                # Success — clean up old backups
                old_backup = path.with_suffix(path.suffix + ".bak.old")
                if old_backup.exists():
                    old_backup.unlink(missing_ok=True)
                return
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
            if attempt < _SAVE_RETRIES:
                logger.warning(
                    "State save attempt %d/%d failed for %s: %s",
                    attempt,
                    _SAVE_RETRIES,
                    path,
                    e,
                )
            else:
                logger.exception(
                    "Failed to persist state after %d attempts to %s",
                    _SAVE_RETRIES,
                    path,
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
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        logger.exception("Failed to serialize semantic world state")

    # Capture the snapshot /before/ submitting to the executor so the
    # background thread sees a consistent view — the store dicts may
    # change between ``.submit()`` and the actual write.
    payload = {
        "saved_at": _now_iso(),
        "jobs": [job.model_dump() for job in jobs_store.values()],
        "recycle_bin": [job.model_dump() for job in recycle_bin_store.values()],
        "world_state": world_state_data,
    }

    try:
        # L7: don't silently drop the write when the executor has been
        # shut down — recover by allocating a fresh executor so the
        # writer thread is restored. The previous branch logged and
        # returned, leaving any post-shutdown state edits permanently
        # in-memory.
        executor = _ensure_save_executor()
        try:
            executor.submit(_write_state_to_disk, path, payload)
        except RuntimeError:
            # Concurrent shutdown reseated ``_SAVE_EXECUTOR`` between
            # our lookup and submit. Re-acquire via the factory and
            # retry once before giving up.
            executor = _get_or_build_save_executor()
            executor.submit(_write_state_to_disk, path, payload)
    except RuntimeError:
        logger.exception("Unable to schedule state save; state may be lost on shutdown")


def flush_state_writes() -> None:
    """Wait for all pending background state writes to complete.

    Should be called during graceful shutdown to ensure no state is lost.
    This is a synchronous call that blocks until all pending writes finish.
    """
    global _SAVE_EXECUTOR
    # L6: take the executor lock for the swap so a racing save_state
    # doesn't observe a half-rebuilt pool. ``executor`` is captured
    # under the lock so a concurrent ``save_state`` only sees either
    # the old (drained) or the new (live) executor — never a half-state.
    with _EXECUTOR_LOCK:
        current = _SAVE_EXECUTOR
    if current is not None:
        current.shutdown(wait=True)
    # Recreate executor for any future writes
    with _EXECUTOR_LOCK:
        _SAVE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="state_store_writer",
        )


def shutdown_state_writes() -> None:
    """Drain and close the background state executor without recreating it."""
    global _SAVE_EXECUTOR
    with _EXECUTOR_LOCK:
        current = _SAVE_EXECUTOR
        _SAVE_EXECUTOR = None
    if current is not None:
        current.shutdown(wait=True)


atexit.register(shutdown_state_writes)
