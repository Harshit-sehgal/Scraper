"""Cross-process JSON-backed KV store.

Owns the persistent JSON file that backs several DataForge routers
(AuthProfile, Workflow, Scheduled Monitoring) so writes from any
worker are immediately visible to any other worker opening the
same path. Mirrors the proven ``fcntl.flock`` + ``os.replace`` +
``os.fsync`` pattern from ``_SubscriptionStore``.

Read operations always re-read disk on every call. Write
operations mutate an in-memory snapshot under an exclusive flock
over a sibling ``.lock`` file so two concurrent processes cannot
clobber each other.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def default_path_for(env_var: str, filename: str) -> Path:
    """Resolve an on-disk path from an env override.

    Reads ``env_var`` on every call so tests can override it after
    import and operators can repoint the store without restarting
    running workers.
    """
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return Path(env_value)
    return Path(__file__).resolve().parents[2] / "data" / filename


def _is_production_env() -> bool:
    try:
        from app.config import settings
    except ImportError:
        return False
    return (getattr(settings, "ENV", "") or "").strip().lower() == "production"


def _utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as ISO-8601.

    Module-level so subclasses and unit tests can import the same
    formatter without re-implementing timezone serialization.
    """
    return datetime.now(UTC).isoformat()


class JSONFileStore:
    """JSON-on-disk key-value registry (per-key records are dicts).

    Persistence model:

    * ``get`` / ``values`` / ``__len__`` re-read disk on every call
      (no in-memory cache) so writes from sibling workers are
      immediately visible.
    * ``upsert`` / ``delete`` / ``merge`` / ``clear_all`` use
      ``_read_modify_write`` which takes an exclusive ``fcntl.flock``
      over the sibling ``.lock`` file then does an atomic
      ``tempfile.mkstemp`` + ``os.replace`` after ``os.fsync``.
    * ``threading.RLock`` guards in-process concurrent readers.

    Failure tolerance:

    * ENOSYS / EOPNOTSUPP from ``flock`` is refused in production
      (cold-fail rather than silently corrupt on NFS / FUSE);
      allowed in non-production with a debug log so tests still run.
    * Unreadable / corrupt / wrong-shape files are tolerated: the
      store starts empty with a warning rather than 500ing on
      startup.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = Path(path) if path is not None else self._default_path()
        self._lock = threading.RLock()

    # ---- subclass hook ----
    def _default_path(self) -> Path:
        """Concrete subclasses (or instances) override this to provide
        the default on-disk path when ``path`` is not supplied.
        Default uses ``./data/store.json``."""
        return Path(__file__).resolve().parents[2] / "data" / "store.json"

    # ---- internal I/O ----
    def _read_json(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            logger.warning(
                "JSONFileStore unreadable; starting empty (path=%s)",
                self.path,
            )
            return {}
        if not isinstance(raw, dict):
            logger.warning(
                "JSONFileStore has unexpected shape; starting empty (path=%s)",
                self.path,
            )
            return {}
        return raw

    def _acquire_cross_process_lock(self) -> int:
        lock_path = self.path.parent / (self.path.name + ".lock")
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError as exc:
                if exc.errno in (errno.ENOSYS, errno.EOPNOTSUPP):
                    if _is_production_env():
                        raise
                    logger.debug(
                        "flock unsupported on this filesystem; cross-process safety is not guaranteed (path=%s)",
                        lock_path,
                    )
                else:
                    raise
        except BaseException:
            os.close(lock_fd)
            raise
        return lock_fd

    def _read_modify_write(
        self,
        mutate: Any,
    ) -> dict[str, dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = self._acquire_cross_process_lock()
        try:
            snapshot = self._read_json()
            mutate(snapshot)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".json_store.",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, sort_keys=True, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                with contextlib.suppress(FileNotFoundError):
                    Path(tmp_path).unlink()
                raise
            return snapshot
        finally:
            os.close(lock_fd)

    # ---- public API ----
    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read_json().get(record_id)
            return dict(record) if record is not None else None

    def values(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._read_json().values()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._read_json())

    def upsert(self, record_id: str, record: dict[str, Any]) -> None:
        """Insert-or-replace a record (read-modify-write under flock).

        Lifecycle invariants preserved across replaces:

        * ``created_at`` — preserved if the caller did not supply
          a new value; otherwise the caller's value wins.
        * ``usage_count`` — preserved if the caller did not supply
          a new value; otherwise the caller's value wins.
        * ``updated_at`` — forced to ``now``.

        Callers wanting a hard overwrite (caller's value always
        wins) should call :meth:`merge` with the full new record,
        or pre-strip lifecycle fields on the record dict before
        calling :meth:`upsert`.
        """
        now_iso = _utc_now_iso()

        def _mutate(s: dict[str, dict[str, Any]]) -> None:
            stored = dict(record)
            stored["updated_at"] = now_iso
            prior = s.get(record_id)
            if prior is not None:
                if "created_at" not in stored and "created_at" in prior:
                    stored["created_at"] = prior["created_at"]
                if "usage_count" not in stored:
                    stored["usage_count"] = int(prior.get("usage_count", 0))
            s[record_id] = stored

        self._read_modify_write(_mutate)

    def delete(self, record_id: str) -> bool:
        removed = False

        def _mutate(s: dict[str, dict[str, Any]]) -> None:
            nonlocal removed
            if record_id in s:
                del s[record_id]
                removed = True

        self._read_modify_write(_mutate)
        return removed

    def delete_many(self, record_ids: list[str]) -> int:
        """Remove many records in a single flocked read-modify-write.

        Batch API to avoid N-fold write amplification when a
        caller wants to purge many records owned by a single
        principal (e.g. ``delete-my-data`` purging all of a
        user's workflows in one tick).
        """
        target_ids = set(record_ids)
        removed: list[int] = [0]

        def _mutate(s: dict[str, dict[str, Any]]) -> None:
            for rid in target_ids:
                if rid in s:
                    del s[rid]
                    removed[0] += 1

        self._read_modify_write(_mutate)
        return removed[0]  # post-write; closure-final read of removed[0] is safe

    def merge(
        self,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Merge *fields* into the existing record (read-modify-write).

        Returns the post-merge record, or ``None`` if no record
        with this id exists.
        """
        captured: list[dict[str, Any] | None] = [None]

        def _mutate(s: dict[str, dict[str, Any]]) -> None:
            existing = s.get(record_id)
            if existing is None:
                return
            merged = {**existing, **fields, "updated_at": _utc_now_iso()}
            s[record_id] = merged
            captured[0] = merged

        self._read_modify_write(_mutate)
        return captured[0]

    def clear_all(self) -> int:
        prior: list[int] = [0]

        def _mutate(s: dict[str, dict[str, Any]]) -> None:
            prior[0] = len(s)
            s.clear()

        self._read_modify_write(_mutate)
        return prior[0]
