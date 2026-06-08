"""SQLite persistence adapter — delegates to existing app.job_store functions
with minimal changes, wrapped in the clean JobRepository contract.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from forge_kernel.persistence import JobRepository

if TYPE_CHECKING:
    from forge_kernel.contracts.job import Job

logger = logging.getLogger(__name__)

# Lazy import of the existing SQLite store — minimal porting surface
_job_store = None
_job_store_lock = threading.Lock()


def _get_store():
    global _job_store
    if _job_store is None:
        with _job_store_lock:
            if _job_store is None:
                try:
                    from app.job_store import load_state, persist_state_single, save_state

                    _job_store = {
                        "load_state": load_state,
                        "save_state": save_state,
                        "persist_state_single": persist_state_single,
                    }
                except ImportError:
                    msg = "Cannot import app.job_store — ensure PYTHONPATH includes backend/"
                    raise RuntimeError(msg) from None
    return _job_store


class SQLiteJobRepository(JobRepository):
    """SQLite-backed repository adapter using the existing job_store implementation."""

    backend = "sqlite"

    def load_all(self) -> tuple[dict[str, Job], dict[str, Job], dict | None]:
        store = _get_store()
        jobs, recycle, ws = store["load_state"](recover_in_progress=False)
        return jobs, recycle, ws

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        store = _get_store()
        store["save_state"](jobs, recycle_bin)

    def save_single(self, job: Job) -> None:
        store = _get_store()
        store["persist_state_single"](job)

    def is_cancel_requested(self, job_id: str) -> bool:
        _get_store()  # ensure initialized
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                row = conn.execute(
                    "SELECT cancel_requested FROM jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                return bool(row[0]) if row else False
            finally:
                conn.close()

    def move_to_recycle_bin(self, job_id: str) -> bool:
        _get_store()  # ensure initialized
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                col_names = [d[0] for d in cursor.description]
                row_dict = dict(zip(col_names, row, strict=False))
                conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                import datetime

                row_dict["deleted_at"] = datetime.datetime.now(datetime.UTC).isoformat()
                cols = ", ".join(row_dict.keys())
                ph = ", ".join("?" for _ in row_dict)
                conn.execute(f"INSERT OR REPLACE INTO recycle_bin ({cols}) VALUES ({ph})", list(row_dict.values()))  # noqa: RUF100, S608
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            else:
                return True
            finally:
                conn.close()

    def restore_from_recycle_bin(self, job_id: str) -> bool:
        _get_store()  # use local lazy loader
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                cursor = conn.execute("SELECT * FROM recycle_bin WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                col_names = [d[0] for d in cursor.description]
                row_dict = dict(zip(col_names, row, strict=False))
                conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))
                row_dict.pop("deleted_at", None)
                cols = ", ".join(row_dict.keys())
                ph = ", ".join("?" for _ in row_dict)
                conn.execute(f"INSERT OR REPLACE INTO jobs ({cols}) VALUES ({ph})", list(row_dict.values()))  # noqa: RUF100, S608
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            else:
                return True
            finally:
                conn.close()

    def hard_delete(self, job_id: str) -> bool:
        _get_store()
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                jobs_cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                cursor = conn.execute("DELETE FROM recycle_bin WHERE id = ?", (job_id,))
                deleted = cursor.rowcount or jobs_cursor.rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            else:
                return deleted > 0
            finally:
                conn.close()
