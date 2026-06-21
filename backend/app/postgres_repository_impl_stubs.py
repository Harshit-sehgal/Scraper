"""M4: Postgres repository stubs - minimal implementations for compatibility."""

# File: backend/app/postgres_repository_impl_stubs.py
# These are placeholder implementations for abstract methods in storage_interface.py
# Real implementations should be added before production Postgres deployment

from app.models import Job
from app.storage_interface import JobStore

class PostgresJobStoreStubs(JobStore):
    """M4: Minimal Postgres implementations to replace NotImplementedError."""
    
    def count_results(self, job_id: str) -> int:
        """M4: Placeholder for Postgres result counting."""
        try:
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT COUNT(*) as cnt FROM results WHERE job_id = %s",
                    (job_id,)
                )
                return int(row["cnt"]) if row else 0
        except Exception:
            return 0
    
    def list_recycle_summaries(self, limit: int = 100, cursor: str | None = None) -> list[dict]:
        """M4: Placeholder for Postgres recycle bin listing."""
        try:
            safe_limit = min(int(limit), 500)
            sql = "SELECT id, name, status, deleted_at FROM jobs WHERE deleted_at IS NOT NULL"
            params: list = []
            if cursor:
                sql += " AND created_at < %s"
                params.append(cursor)
            sql += " ORDER BY deleted_at DESC LIMIT %s"
            params.append(safe_limit)
            
            with self._conn() as conn:
                rows = self._fetch_all(conn, sql, tuple(params))
            return [
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "deleted_at": row.get("deleted_at"),
                }
                for row in rows
            ]
        except Exception:
            return []
    
    def count_events(self, job_id: str) -> int:
        """M4: Placeholder for Postgres event counting."""
        try:
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT COUNT(*) as cnt FROM events WHERE job_id = %s",
                    (job_id,)
                )
                return int(row["cnt"]) if row else 0
        except Exception:
            return 0
    
    def save_single(self, job: Job) -> None:
        """M4: Placeholder for single job save."""
        # In production, upsert job record and results
        pass
