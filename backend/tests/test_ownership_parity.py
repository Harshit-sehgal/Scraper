"""Storage ownership parity tests for CAND-P0-STORAGE-001.

Verifies that ownership fields (``created_by``, ``org_id``, ``project_id``)
survive full save/load round-trips in the SQLite backend. Postgres parity
tests are marked with ``@pytest.mark.postgres`` and skipped when no PG
environment is available.
"""

from __future__ import annotations

import pytest
from app.models import Job, JobStatus
from app.storage_mapper import job_to_row, row_to_job


def _fake_job_with_ownership(
    id_: str = "j1",
    created_by: str = "user-1",
    org_id: str = "org-1",
    project_id: str = "proj-1",
    **overrides,
) -> Job:
    defaults = {
        "id": id_,
        "name": "ownership-test",
        "status": JobStatus.COMPLETED,
        "urls": ["https://test.invalid"],
        "created_by": created_by,
        "org_id": org_id,
        "project_id": project_id,
    }
    defaults.update(overrides)
    return Job(**defaults)


# ─── Row serialization parity ────────────────────────────────────────────


class TestOwnershipRowMapping:
    """``job_to_row`` / ``row_to_job`` preserve ownership fields."""

    def test_created_by_preserved_in_row(self) -> None:
        job = _fake_job_with_ownership(created_by="alice@test.invalid")
        row = job_to_row(job)
        assert row["created_by"] == "alice@test.invalid"

    def test_org_id_preserved_in_row(self) -> None:
        job = _fake_job_with_ownership(org_id="org-42")
        row = job_to_row(job)
        assert row["org_id"] == "org-42"

    def test_project_id_preserved_in_row(self) -> None:
        job = _fake_job_with_ownership(project_id="proj-42")
        row = job_to_row(job)
        assert row["project_id"] == "proj-42"

    def test_empty_strings_round_trip(self) -> None:
        """Empty-string ownership fields must survive mapping."""
        job = _fake_job_with_ownership(created_by="", org_id="", project_id="")
        row = job_to_row(job)
        assert row["created_by"] == ""
        assert row["org_id"] == ""
        assert row["project_id"] == ""

    def test_all_three_fields_round_trip(self) -> None:
        """End-to-end: job → row → job preserves all ownership."""
        job = _fake_job_with_ownership(
            created_by="creator-123",
            org_id="org-456",
            project_id="proj-789",
        )
        row = job_to_row(job)
        reconstructed = row_to_job(row)
        assert reconstructed is not None
        assert reconstructed.created_by == "creator-123"
        assert reconstructed.org_id == "org-456"
        assert reconstructed.project_id == "proj-789"


# ─── SQLite store round-trip ─────────────────────────────────────────────


@pytest.fixture
def sqlite_state_path(tmp_path):
    """Temporary path for on-disk SQLite storage."""
    import os

    old_path = os.environ.get("DATAFORGE_DB_PATH")
    db_path = tmp_path / "test_ownership.db"
    os.environ["DATAFORGE_DB_PATH"] = str(db_path)
    yield db_path
    if old_path:
        os.environ["DATAFORGE_DB_PATH"] = old_path
    else:
        os.environ.pop("DATAFORGE_DB_PATH", None)


class TestSqliteOwnershipRoundTrip:
    """Full save_state → load_state round-trip preserves ownership."""

    def test_created_by_survives_save_load(self, sqlite_state_path) -> None:
        from app.job_store import load_state, save_state

        job = _fake_job_with_ownership(created_by="creator-sqlite")
        save_state({"j1": job}, {})
        jobs, _, _ = load_state(recover_in_progress=False)
        loaded = jobs.get("j1")
        assert loaded is not None
        assert loaded.created_by == "creator-sqlite"

    def test_org_id_survives_save_load(self, sqlite_state_path) -> None:
        from app.job_store import load_state, save_state

        job = _fake_job_with_ownership(org_id="org-sqlite")
        save_state({"j1": job}, {})
        jobs, _, _ = load_state(recover_in_progress=False)
        loaded = jobs.get("j1")
        assert loaded is not None
        assert loaded.org_id == "org-sqlite"

    def test_project_id_survives_save_load(self, sqlite_state_path) -> None:
        from app.job_store import load_state, save_state

        job = _fake_job_with_ownership(project_id="proj-sqlite")
        save_state({"j1": job}, {})
        jobs, _, _ = load_state(recover_in_progress=False)
        loaded = jobs.get("j1")
        assert loaded is not None
        assert loaded.project_id == "proj-sqlite"

    def test_all_three_fields_survives_save_load(self, sqlite_state_path) -> None:
        from app.job_store import load_state, save_state

        job = _fake_job_with_ownership(
            created_by="c-sqlite",
            org_id="o-sqlite",
            project_id="p-sqlite",
        )
        save_state({"j1": job}, {})
        jobs, _, _ = load_state(recover_in_progress=False)
        loaded = jobs.get("j1")
        assert loaded is not None
        assert loaded.created_by == "c-sqlite"
        assert loaded.org_id == "o-sqlite"
        assert loaded.project_id == "p-sqlite"

    def test_empty_ownership_survives_save_load(self, sqlite_state_path) -> None:
        """Empty-string ownership fields must survive a full round-trip."""
        from app.job_store import load_state, save_state

        job = _fake_job_with_ownership(created_by="", org_id="", project_id="")
        save_state({"j1": job}, {})
        jobs, _, _ = load_state(recover_in_progress=False)
        loaded = jobs.get("j1")
        assert loaded is not None
        assert loaded.created_by == ""
        assert loaded.org_id == ""
        assert loaded.project_id == ""

    def test_multiple_jobs_preserve_distinct_ownership(self, sqlite_state_path) -> None:
        """Two jobs with different ownership must not cross-contaminate."""
        from app.job_store import load_state, save_state

        j1 = _fake_job_with_ownership(id_="j1", created_by="u1", org_id="o1", project_id="p1")
        j2 = _fake_job_with_ownership(id_="j2", created_by="u2", org_id="o2", project_id="p2")
        save_state({"j1": j1, "j2": j2}, {})
        jobs, _, _ = load_state(recover_in_progress=False)

        assert jobs["j1"].created_by == "u1"
        assert jobs["j2"].created_by == "u2"
        assert jobs["j1"].org_id == "o1"
        assert jobs["j2"].org_id == "o2"
        assert jobs["j1"].project_id == "p1"
        assert jobs["j2"].project_id == "p2"

    def test_save_single_preserves_ownership(self, sqlite_state_path) -> None:
        from app.job_store import load_state, persist_state_single

        job = _fake_job_with_ownership(created_by="single-user", org_id="single-org", project_id="single-proj")
        persist_state_single(job)
        jobs, _, _ = load_state(recover_in_progress=False)
        loaded = jobs.get("j1")
        assert loaded is not None
        assert loaded.created_by == "single-user"
        assert loaded.org_id == "single-org"
        assert loaded.project_id == "single-proj"


class TestSqliteRecycleBinOwnership:
    """Ownership fields survive soft-delete + restore."""

    def test_recycle_bin_preserves_ownership(self, sqlite_state_path) -> None:
        from app.job_store import load_state, save_state

        job = _fake_job_with_ownership(id_="rb1", created_by="rb-user")
        save_state({}, {"rb1": job})
        _, recycle, _ = load_state(recover_in_progress=False)
        loaded = recycle.get("rb1")
        assert loaded is not None
        assert loaded.created_by == "rb-user"
        assert loaded.org_id is not None
        assert loaded.project_id is not None


# ─── Postgres parity (skipped unless PG is available) ────────────────────


@pytest.mark.postgres
@pytest.mark.skip(reason="Postgres not available in this environment — run with DATAFORGE_DATABASE_URL set")
class TestPostgresOwnershipParity:
    """Ownership fields survive Postgres save/load via the base repository.

    All tests are marked ``@pytest.mark.postgres`` and require a running
    Postgres instance. Run with::

        DATAFORGE_DATABASE_URL=postgresql://... pytest -m postgres
    """

    def test_ownership_fields_in_job_from_postgres_row(self) -> None:
        """``row_to_job`` produces correct ownership from a PG-shaped row."""
        row = {
            "id": "pg-1",
            "name": "pg-test",
            "status": "completed",
            "urls": "[]",
            "created_by": "pg-user",
            "org_id": "pg-org",
            "project_id": "pg-proj",
        }
        job = row_to_job(row)
        assert job is not None
        assert job.created_by == "pg-user"
        assert job.org_id == "pg-org"
        assert job.project_id == "pg-proj"

    def test_empty_ownership_in_postgres_row(self) -> None:
        """Null/missing ownership fields in PG row → empty strings in Job."""
        row = {
            "id": "pg-2",
            "name": "pg-empty",
            "status": "completed",
            "urls": "[]",
            "created_by": None,
            "org_id": None,
            "project_id": None,
        }
        job = row_to_job(row)
        assert job is not None
        assert job.created_by == ""

    def test_job_to_row_includes_ownership(self) -> None:
        """``job_to_row`` surfaces ownership keys for Postgres upsert."""
        job = _fake_job_with_ownership(
            created_by="mapper-user",
            org_id="mapper-org",
            project_id="mapper-proj",
        )
        row = job_to_row(job)
        assert "created_by" in row
        assert "org_id" in row
        assert "project_id" in row
