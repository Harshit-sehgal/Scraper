import pytest
from app.models import Job, JobStatus
from app.storage_interface import SQLiteJobRepository


@pytest.fixture(autouse=True)
def clean_job_store():
    from app.job_store import _DB_LOCK, _get_connection, reset_job_store_for_tests

    reset_job_store_for_tests()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM recycle_bin")
            conn.commit()
        finally:
            conn.close()


def test_sqlite_repository_atomic_move_and_restore():
    repo = SQLiteJobRepository()

    # 1. Create a job
    job = Job(
        name="atomic-test-job",
        mode="manual",
        urls=["http://atomic.com"],
        schema_fields=[{"name": "field", "field_type": "string"}],
    )
    repo.save_single(job)

    # Verify present in active jobs
    jobs = repo.load_jobs()
    assert job.id in jobs
    assert len(repo.load_recycle_bin()) == 0

    # 2. Move to recycle bin
    moved = repo.move_to_recycle_bin(job.id)
    assert moved is True

    # Verify no longer active, now in recycle bin
    assert job.id not in repo.load_jobs()
    recycle = repo.load_recycle_bin()
    assert job.id in recycle

    # 3. Restore
    restored = repo.restore_from_recycle_bin(job.id)
    assert restored is True

    # Verify active again, gone from recycle bin
    assert job.id in repo.load_jobs()
    assert len(repo.load_recycle_bin()) == 0


def test_sqlite_repository_atomic_hard_delete():
    repo = SQLiteJobRepository()

    job = Job(name="delete-test-job", mode="manual", urls=["http://delete.com"], schema_fields=[])
    repo.save_single(job)

    # Move to recycle bin
    repo.move_to_recycle_bin(job.id)
    assert job.id in repo.load_recycle_bin()

    # Hard delete
    deleted = repo.hard_delete(job.id)
    assert deleted is True
    assert job.id not in repo.load_recycle_bin()
    assert job.id not in repo.load_jobs()


def test_sqlite_repository_clear_terminal_jobs():
    repo = SQLiteJobRepository()

    # Active job
    job_active = Job(name="active-job", mode="manual", urls=["http://active.com"], schema_fields=[])
    job_active.status = JobStatus.RUNNING
    repo.save_single(job_active)

    # Terminal job
    job_terminal = Job(name="terminal-job", mode="manual", urls=["http://terminal.com"], schema_fields=[])
    job_terminal.status = JobStatus.COMPLETED
    repo.save_single(job_terminal)

    # Clear terminal jobs
    cleared = repo.clear_terminal_jobs()
    assert cleared == 1

    # Verify active job is untouched
    assert job_active.id in repo.load_jobs()

    # Verify terminal job was moved to recycle bin
    assert job_terminal.id not in repo.load_jobs()
    assert job_terminal.id in repo.load_recycle_bin()
