"""M8: Data retention enforcement tests."""
import datetime
from app.utils.data_retention import enforce_retention, get_retention_config


def test_retention_config_defaults() -> None:
    """M8: Retention config has sensible defaults."""
    config = get_retention_config()
    
    assert config["completed_jobs_days"] >= 7, "M8: Completed jobs retention >= 7 days"
    assert config["recycle_bin_days"] >= 1, "M8: Recycle bin retention >= 1 day"
    assert config["idempotency_keys_days"] >= 1, "M8: Idempotency key retention >= 1 day"


def test_enforce_retention_dry_run() -> None:
    """M8: Dry run doesn't delete anything."""
    from app.models import Job, JobStatus
    
    old_job = Job(
        id="job1",
        name="test",
        urls=["https://example.com"],
        mode="fast",
        created_by="test-user",
        status=JobStatus.COMPLETED,
    )
    old_job.completed_at = (datetime.datetime.now() - datetime.timedelta(days=100)).isoformat()
    
    jobs_store = {"job1": old_job}
    recycle = {}
    
    result = enforce_retention(jobs_store, recycle, dry_run=True)
    
    # M8: Should report what would be deleted but not delete
    assert result["jobs_purged"] >= 0, "M8: Dry run should count"
    assert len(jobs_store) == 1, "M8: Dry run should not delete"


def test_enforce_retention_deletes_old_jobs() -> None:
    """M8: Old jobs are deleted."""
    from app.models import Job, JobStatus
    
    old_job = Job(
        id="old_job",
        name="old",
        urls=["https://example.com"],
        mode="fast",
        created_by="test-user",
        status=JobStatus.COMPLETED,
    )
    old_job.completed_at = (datetime.datetime.now() - datetime.timedelta(days=95)).isoformat()
    
    new_job = Job(
        id="new_job",
        name="new",
        urls=["https://example.com"],
        mode="fast",
        created_by="test-user",
        status=JobStatus.COMPLETED,
    )
    new_job.completed_at = datetime.datetime.now().isoformat()
    
    jobs_store = {"old_job": old_job, "new_job": new_job}
    recycle = {}
    
    result = enforce_retention(jobs_store, recycle, dry_run=False)
    
    # M8: Old job should be deleted
    assert "old_job" not in jobs_store, "M8: Old job should be purged"
    assert "new_job" in jobs_store, "M8: New job should remain"
    assert result["jobs_purged"] >= 1, "M8: Should report purge"


def test_retention_respects_retention_days() -> None:
    """M8: Retention respects configured days."""
    from app.models import Job, JobStatus
    
    config = get_retention_config()
    days = config["completed_jobs_days"]
    
    # Job older than retention window
    expired_job = Job(
        id="expired",
        name="expired",
        urls=["https://example.com"],
        mode="fast",
        created_by="test-user",
        status=JobStatus.COMPLETED,
    )
    expired_job.completed_at = (datetime.datetime.now() - datetime.timedelta(days=days + 1)).isoformat()
    
    jobs_store = {"expired": expired_job}
    
    result = enforce_retention(jobs_store, {}, dry_run=False)
    assert "expired" not in jobs_store, "M8: Should delete expired job"
