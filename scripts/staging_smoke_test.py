import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add backend directory to path so we can import from backend app
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Configure temporary state database file path
temp_db_dir = tempfile.mkdtemp()
temp_state_file = Path(temp_db_dir) / "staging_jobs_state.json"
temp_db_file = Path(temp_db_dir) / "staging_jobs_state.db"

os.environ["STATE_FILE_PATH"] = str(temp_state_file)

# Set settings environment variable if it overrides
from app.config import settings

settings.STATE_FILE_PATH = str(temp_state_file)

from app.job_store import _get_connection, load_state, reset_job_store_for_tests
from app.main import app
from app.models import JobStatus
from fastapi.testclient import TestClient

client = TestClient(app)


def _check(condition: bool, message: str) -> None:
    """Runtime check for the drill script. Used instead of ``assert`` so the
    script keeps working when run with ``python -O`` (which strips asserts)."""
    if not condition:
        raise SystemExit(f"DRILL CHECK FAILED: {message}")


def run_drill():
    print("======================================================================")
    print("🚀 STARTING AUTOMATED DATA FORGE PRODUCTION-STAGING SMOKE TEST DRILL")
    print("======================================================================")

    # 1. Clean the store
    reset_job_store_for_tests()

    # 2. Create 5 Manual Scraping Jobs
    print("\n[Step 1 & 2] Creating 5 Manual Scraping Jobs...")
    manual_job_ids = []
    for i in range(1, 6):
        response = client.post(
            "/api/jobs",
            json={
                "name": f"Manual Job {i}",
                "mode": "manual",
                "intent": "Extract flight numbers and prices",
                "urls": [f"https://manualdomain{i}.com/flights"],
                "schema_fields": [
                    {"name": "flight_no", "field_type": "string", "required": True},
                    {"name": "price", "field_type": "number", "required": True},
                ],
                "filters": [],
                "min_record_score": 0.4,
            },
        )
        _check(response.status_code == 200, f"Failed to create manual job {i}: {response.text}")
        job_data = response.json()
        manual_job_ids.append(job_data["job_id"])
        print(f"  - Created Manual Job ID: {job_data['job_id']}")

    # 3. Create 2 Auto-Discovery Jobs
    print("\n[Step 2 cont.] Creating 2 Auto-Discovery Jobs...")
    auto_job_ids = []
    for i in range(1, 3):
        response = client.post(
            "/api/jobs",
            json={
                "name": f"Auto Discovery Job {i}",
                "mode": "auto",
                "intent": "Discover flight tickets",
                "topic": "flights",
                "location": "London",
                "preferred_domain": f"autodomain{i}.com",
                "schema_fields": [{"name": "price", "field_type": "number", "required": True}],
                "filters": [],
                "min_record_score": 0.35,
            },
        )
        _check(response.status_code == 200, f"Failed to create auto job {i}: {response.text}")
        job_data = response.json()
        auto_job_ids.append(job_data["job_id"])
        print(f"  - Created Auto Job ID: {job_data['job_id']}")

    # 4. Cancel 1 manual job while active
    print("\n[Step 3] Cancelling 1 job...")
    cancel_job_id = manual_job_ids[0]
    response = client.post(f"/api/jobs/{cancel_job_id}/cancel")
    _check(response.status_code == 200, f"Failed to cancel job: {response.text}")
    cancel_data = response.json()
    _check(cancel_data["cancel_requested"] is True, "Cancel request flag was not set!")
    print(f"  - Successfully set cancel_requested=True for Job ID: {cancel_job_id}")

    # 5. Simulate a hard server crash / ungraceful termination
    print("\n[Step 4 & 5] Simulating server crash while 1 job is RUNNING...")
    crash_job_id = manual_job_ids[1]

    # Write directly to SQLite to simulate a running job that was cut off by process kill
    conn = _get_connection()
    with conn:
        conn.execute("UPDATE jobs SET status = ?, logs = ? WHERE id = ?", (JobStatus.RUNNING.value, "[]", crash_job_id))
    print(f"  - Directly updated Job ID: {crash_job_id} to status='running' in database to simulate crash.")

    # 6. Restart/Reload the server
    print("\n[Step 6] Restarting server and reloading job state...")
    reset_job_store_for_tests()
    loaded_jobs, loaded_recycle, _ = load_state()
    from app.main import jobs_store, recycle_bin_store

    jobs_store.clear()
    jobs_store.update(loaded_jobs)
    recycle_bin_store.clear()
    recycle_bin_store.update(loaded_recycle)

    # 7. Confirm the interrupted job becomes FAILED with restart recovery log
    print("\n[Step 7] Confirming the interrupted job transitioned to FAILED...")
    interrupted_job = loaded_jobs.get(crash_job_id)
    if interrupted_job is None:
        raise SystemExit("DRILL CHECK FAILED: Interrupted job not found after reload!")
    _check(interrupted_job.status == JobStatus.FAILED, f"Interrupted job status is {interrupted_job.status}, expected FAILED!")

    # Verify the restart recovery message exists on the job error attribute
    _check(interrupted_job.error is not None, "Interrupted job did not contain an error message!")
    error_text = (interrupted_job.error or "").lower()
    _check(
        "restart" in error_text or "recovery" in error_text or "recovered" in error_text,
        f"Unexpected error message: {interrupted_job.error}",
    )
    print(f"  - Verified recovery error: {interrupted_job.error}")
    print("  - Interrupted job successfully recovered to FAILED status.")

    # 8. Confirm completed or other jobs still load from SQLite
    print("\n[Step 8] Confirming other jobs load normally from SQLite...")
    _check(len(loaded_jobs) == 7, f"Expected 7 jobs in store, found {len(loaded_jobs)}!")
    print("  - Loaded all 7 jobs successfully.")

    # 9. Confirm /api/system/status is healthy
    print("\n[Step 9] Confirming /api/system/status and /api/storage/status endpoint status...")
    response = client.get("/api/system/status")
    _check(response.status_code == 200, f"Health check failed: {response.text}")
    health_data = response.json()
    _check(health_data["status"] == "online", f"Health status is {health_data['status']}, expected online!")
    print(f"  - System Status: {health_data}")

    # Also verify SQLite Storage backend
    response = client.get("/api/system/storage/status")
    _check(response.status_code == 200, f"Storage status failed: {response.text}")
    storage_data = response.json()
    _check(storage_data["backend"] == "sqlite", f"Expected sqlite, found {storage_data['backend']}")
    _check(storage_data["wal_mode"] == "wal", f"Expected wal mode, found {storage_data['wal_mode']}")
    print(f"  - Storage Status: {storage_data}")

    # 10. Confirm results export works
    print("\n[Step 10] Confirming results export works...")
    export_job_id = manual_job_ids[2]
    # Update the in-memory job results and persist it to SQLite
    from app.job_store import persist_state_single
    from app.main import jobs_store

    job = jobs_store[export_job_id]
    job.results = [{"flight_no": "AA123", "price": 450.0}]
    persist_state_single(job)
    # Get the job results
    response = client.get(f"/api/jobs/{export_job_id}")
    _check(response.status_code == 200, f"Failed to get job: {response.text}")
    job_details = response.json()
    _check(len(job_details["results"]) == 1, "Results failed to serialize/deserialize!")
    _check(job_details["results"][0]["flight_no"] == "AA123", "Result data mismatch!")
    print(f"  - Verified results offload & export for Job ID: {export_job_id}: {job_details['results']}")

    # 11. Confirm recycle-bin actions work
    print("\n[Step 11] Confirming recycle-bin actions work...")
    delete_job_id = manual_job_ids[3]

    # Cancel the pending job so it transitions to CANCELED and becomes deletable
    client.post(f"/api/jobs/{delete_job_id}/cancel")

    # Delete the job (moves it to recycle bin)
    response = client.delete(f"/api/jobs/{delete_job_id}")
    _check(response.status_code == 200, f"Failed to move job to recycle bin: {response.text}")

    # Verify it is not listed in active jobs list
    response = client.get("/api/jobs")
    active_jobs = response.json()["jobs"]
    _check(delete_job_id not in [j["id"] for j in active_jobs], "Deleted job still listed as active!")

    # Check recycle bin list
    response = client.get("/api/recycle_bin")
    _check(response.status_code == 200, f"Failed to fetch recycle bin: {response.text}")
    bin_jobs = response.json()["jobs"]
    _check(delete_job_id in [j["id"] for j in bin_jobs], "Deleted job not found in recycle bin!")
    print(f"  - Verified job {delete_job_id} is in recycle bin.")

    # Restore the job
    response = client.post(f"/api/recycle_bin/{delete_job_id}/restore")
    _check(response.status_code == 200, f"Failed to restore job: {response.text}")

    # Verify it is back in active list
    response = client.get("/api/jobs")
    active_jobs = response.json()["jobs"]
    _check(delete_job_id in [j["id"] for j in active_jobs], "Restored job not listed as active!")
    print(f"  - Verified job {delete_job_id} successfully restored from recycle bin.")

    print("\n======================================================================")
    print("🎉 ALL STAGING DRILL DURABILITY AND STATE INVARIANTS FULLY PASSED!")
    print("======================================================================")


if __name__ == "__main__":
    try:
        run_drill()
    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_db_dir)
