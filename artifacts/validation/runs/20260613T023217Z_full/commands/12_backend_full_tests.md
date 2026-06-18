# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T02:32:32.673420+00:00
- end_time: 2026-06-13T02:36:11.008293+00:00
- duration_seconds: 218.35
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: true

## stdout

```text
........................................................................ [  2%]
..................................................................F.F... [  4%]
........................................................................ [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................................................ [ 18%]
..................s..................................................... [ 20%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
.............................................ssssssss................... [ 32%]
........................................................................ [ 34%]
................FFFFF.................s....FFFF..F.FFF.Fs............... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
..............................................................F......F.. [ 46%]
........................................................................ [ 48%]
....................................................ssssssssssssssssssss [ 50%]
ss...........................ss......................................... [ 52%]
............................ss.......................................... [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
...........................................sssssssssssss................ [ 60%]
...................s.................................................... [ 62%]
........................................................................ [ 64%]
.............................................FFFF....................... [ 66%]
.................................................F.FFF.................. [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
.............sssssss.................................................... [ 84%]
...........................................................F............ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
.........................................................s.............. [ 96%]
.....ss..sssssssssssssssssss............................................ [ 98%]
........................................................................ [100%]
=================================== FAILURES ===================================
____ TestWorkerPicksQueuedJob.test_worker_picks_queued_job_and_updates_repo ____

self = <tests.test_api_worker_integration.TestWorkerPicksQueuedJob object at 0x786efd1374d0>
client = <tests.test_api_worker_integration.LocalASGIClient object at 0x786ef78e3410>
tmp_queue_db = PosixPath('/tmp/pytest-of-harshit/pytest-497/test_worker_picks_queued_job_a0/worker_queue.db')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef78e25a0>

    @pytest.mark.asyncio
    async def test_worker_picks_queued_job_and_updates_repo(self, client, tmp_queue_db, monkeypatch) -> None:
        """Worker should dequeue a job, process it, and update the repository."""
        import asyncio

        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

        queue = get_worker_queue(db_path=tmp_queue_db)

        # Register a mock handler that simulates job completion
        async def mock_handler(task):
            from app.config import settings
            from app.services.job_runner import run_job
            from app.storage_interface import get_job_repository

            job_id = task.payload.get("job_id")
            repo = get_job_repository()
            jobs_store, recycle_bin_store, _ = repo.load_all()

            job = jobs_store.get(job_id)
            if not job:
                msg = f"Job not found: {job_id}"
                raise ValueError(msg)

            await run_job(
                job_id=job_id,
                jobs_store=jobs_store,
                persist_state_fn=lambda: repo.save_all(jobs_store, recycle_bin_store),
                max_discovery_urls=settings.MAX_DISCOVERY_URLS,
                max_job_runtime_seconds=settings.MAX_JOB_RUNTIME_SECONDS,
                per_url_scrape_timeout_seconds=settings.PER_URL_TIMEOUT_SECONDS,
                ai_structuring_timeout_seconds=settings.AI_STRUCTURING_TIMEOUT_SECONDS,
                insight_timeout_seconds=settings.INSIGHT_TIMEOUT_SECONDS,
                persist_state_single_fn=lambda: repo.save_single(jobs_store[job_id]),
                persist_state_single_critical_fn=lambda: repo.save_single(jobs_store[job_id]),
            )
            return {
                "job_id": job_id,
                "status": job.status.value,
                "total_records": job.total_records,
            }

        queue.register_handler("scrape_job", mock_handler)

        # Create a job via API
        response = await client.post(
            "/api/jobs",
            json={
                "name": "Worker Pickup Test",
                "mode": "manual",
                "urls": ["https://example.com"],
            },
        )
>       assert response.status_code == 200
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_api_worker_integration.py:211: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_______ TestRealWorkerHandler.test_real_worker_handler_executes_via_api ________

self = <tests.test_api_worker_integration.TestRealWorkerHandler object at 0x786efd15e240>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-497/test_real_worker_handler_execu0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786efd11f620>

    @pytest.mark.asyncio
    async def test_real_worker_handler_executes_via_api(self, tmp_path, monkeypatch) -> None:
        """End-to-end test using the real scrape_job_handler from scripts/run_worker.

        Flow:
        1. Import the real scrape_job_handler from scripts.run_worker
        2. Mock scrape_url_with_recovery to return sample records
        3. Create job through API
        4. Dequeue task from WorkerQueue
        5. Execute real scrape_job_handler(task)
        6. Assert repository job reaches terminal status
        """
        import asyncio
        import sys

        from app.worker_queue import get_worker_queue, reset_worker_queue

        # ── Ensure project root is on path for scripts.run_worker import ─
        project_root = str(Path(__file__).resolve().parents[2])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from scripts.run_worker import scrape_job_handler

        # ── Mock scraped records ─────────────────────────────────────────
        async def mock_scrape_url_with_recovery(
            url,
            schema_fields,
            min_record_score=0.35,
            user_intent="",
            world_state=None,
            max_recovery_attempts=3,
            selectors_map=None,
            search_params=None,
            usage_context=None,
        ):
            sample_records = [
                {
                    "name": "RealHandler Widget A",
                    "price": 9.99,
                    "source_url": url,
                    "source_type": "direct",
                    "source_trust_score": 0.95,
                },
            ]
            recovery_stats = {"recovery_attempts": 0, "recovery_actions_taken": [], "acquisition_lineage": {}}
            return sample_records, recovery_stats

        monkeypatch.setattr(
            "app.scraper_recovery_integration.scrape_url_with_recovery",
            mock_scrape_url_with_recovery,
        )
        monkeypatch.setattr(
            "app.services.job_runner.scrape_url_with_recovery",
            mock_scrape_url_with_recovery,
        )

        async def mock_generate_data_insight(results) -> str:
            return "Mock insight for worker integration test."

        monkeypatch.setattr("app.scraper.generate_data_insight", mock_generate_data_insight)

        # ── Setup: enable worker queue, point SQLite at temp path ───────
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "true")

        from app.config import settings
        from app.job_store import reset_job_store_for_tests

        db_file = tmp_path / "test_real_handler_jobs.db"
        state_file = db_file.with_suffix(".json")
        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
        reset_job_store_for_tests()

        from app.main import jobs_store, recycle_bin_store

        jobs_store.clear()
        recycle_bin_store.clear()

        reset_worker_queue()
        queue = get_worker_queue(db_path=tmp_path / "test_real_handler_queue.db")
        queue.register_handler("scrape_job", scrape_job_handler)

        from app.main import app as main_app

        ac = LocalASGIClient(main_app)

        # ── Step 1: Create job via API ──────────────────────────────────
        response = await ac.post(
            "/api/jobs",
            json={
                "name": "Real Handler E2E",
                "mode": "manual",
                "urls": ["https://example.com/products"],
            },
        )
>       assert response.status_code == 200, f"API returned {response.status_code}: {response.text}"
E       AssertionError: API returned 429: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_api_worker_integration.py:348: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
________ TestIdempotencyHappyPath.test_repeated_key_returns_same_job_id ________

self = <tests.test_idempotency_keys.TestIdempotencyHappyPath object at 0x786efc8359a0>
client = <tests.conftest.LocalASGIClient object at 0x786ef451b7d0>

    def test_repeated_key_returns_same_job_id(self, client) -> None:
        headers = {"X-API-Key": "test", "Idempotency-Key": "client-retry-001"}
        first = client.post("/api/jobs", json=_create_payload("1"), headers=headers)
>       assert first.status_code == 200, first.text
E       AssertionError: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_idempotency_keys.py:26: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_ TestIdempotencyHappyPath.test_repeated_key_with_different_payload_returns_409 _

self = <tests.test_idempotency_keys.TestIdempotencyHappyPath object at 0x786efc835040>
client = <tests.conftest.LocalASGIClient object at 0x786ef45b3710>

    def test_repeated_key_with_different_payload_returns_409(self, client) -> None:
        headers = {"X-API-Key": "test", "Idempotency-Key": "client-retry-conflict"}
        first = client.post("/api/jobs", json=_create_payload("A"), headers=headers)
>       assert first.status_code == 200, first.text
E       AssertionError: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_idempotency_keys.py:39: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
______ TestIdempotencyHappyPath.test_different_keys_create_different_jobs ______

self = <tests.test_idempotency_keys.TestIdempotencyHappyPath object at 0x786efc8379b0>
client = <tests.conftest.LocalASGIClient object at 0x786ef45b0950>

    def test_different_keys_create_different_jobs(self, client) -> None:
        h1 = {"X-API-Key": "test", "Idempotency-Key": "key-A"}
        h2 = {"X-API-Key": "test", "Idempotency-Key": "key-B"}
        a = client.post("/api/jobs", json=_create_payload("A"), headers=h1)
        b = client.post("/api/jobs", json=_create_payload("B"), headers=h2)
>       assert a.status_code == 200
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_idempotency_keys.py:50: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
___________ TestIdempotencyHappyPath.test_no_header_means_no_replay ____________

self = <tests.test_idempotency_keys.TestIdempotencyHappyPath object at 0x786efc837e00>
client = <tests.conftest.LocalASGIClient object at 0x786ef45c92b0>

    def test_no_header_means_no_replay(self, client) -> None:
        h = {"X-API-Key": "test"}
        a = client.post("/api/jobs", json=_create_payload("X"), headers=h)
        b = client.post("/api/jobs", json=_create_payload("Y"), headers=h)
>       assert a.json()["idempotent_replay"] is False
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'idempotent_replay'

backend/tests/test_idempotency_keys.py:60: KeyError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
___________ TestIdempotencyValidation.test_overlong_key_is_rejected ____________

self = <tests.test_idempotency_keys.TestIdempotencyValidation object at 0x786efc850320>
client = <tests.conftest.LocalASGIClient object at 0x786ef45b36b0>

    def test_overlong_key_is_rejected(self, client) -> None:
        headers = {"X-API-Key": "test", "Idempotency-Key": "x" * 200}
        r = client.post("/api/jobs", json=_create_payload(), headers=headers)
>       assert r.status_code == 400
E       assert 429 == 400
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_idempotency_keys.py:69: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
________________ test_double_cancel_terminal_job_returns_early _________________

client = <tests.conftest.LocalASGIClient object at 0x786ef451a030>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef456a720>

    def test_double_cancel_terminal_job_returns_early(client, monkeypatch) -> None:
        """Canceling a job that is already in a terminal status returns 'already in terminal'."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:47:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef451a030>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
___________________ test_cancel_active_job_sets_request_flag ___________________

client = <tests.conftest.LocalASGIClient object at 0x786ef451be60>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786efc834aa0>

    def test_cancel_active_job_sets_request_flag(client, monkeypatch) -> None:
        """Canceling a RUNNING job sets cancel_requested without changing status."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:68:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef451be60>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_____________________ test_cancel_pending_job_auto_cancels _____________________

client = <tests.conftest.LocalASGIClient object at 0x786ef45b3350>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef45b0740>

    def test_cancel_pending_job_auto_cancels(client, monkeypatch) -> None:
        """Canceling a PENDING job auto-cancels it to CANCELED status."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:85:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef45b3350>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
________________ test_delete_terminal_job_moves_to_recycle_bin _________________

client = <tests.conftest.LocalASGIClient object at 0x786ef45c9610>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef45c8050>

    def test_delete_terminal_job_moves_to_recycle_bin(client, monkeypatch) -> None:
        """Deleting a terminal-status job moves it to the recycle bin."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:109:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef45c9610>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
______________________ test_restore_job_from_recycle_bin _______________________

client = <tests.conftest.LocalASGIClient object at 0x786ef45ca870>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef45c81a0>

    def test_restore_job_from_recycle_bin(client, monkeypatch) -> None:
        """Restoring a job from recycle bin puts it back in active jobs."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:143:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef45ca870>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
____________________ test_list_recycle_bin_shows_moved_jobs ____________________

client = <tests.conftest.LocalASGIClient object at 0x786ef4b81d60>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef4b83080>

    def test_list_recycle_bin_shows_moved_jobs(client, monkeypatch) -> None:
        """Listing the recycle bin shows jobs that were moved there."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client, name="list-rb-test")
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:171:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef4b81d60>
name = 'list-rb-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
____________________ test_restore_and_re_delete_round_trip _____________________

client = <tests.conftest.LocalASGIClient object at 0x786ef4b80e90>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef4b82c90>

    def test_restore_and_re_delete_round_trip(client, monkeypatch) -> None:
        """A job can be restored from recycle bin and moved back again."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:187:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef4b80e90>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_____________________ test_hard_delete_removes_permanently _____________________

client = <tests.conftest.LocalASGIClient object at 0x786ef45c9d00>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef45c8050>

    def test_hard_delete_removes_permanently(client, monkeypatch) -> None:
        """Hard deleting from recycle bin removes the job permanently."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:214:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef45c9d00>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_____________________ test_hard_delete_cleans_disk_results _____________________

client = <tests.conftest.LocalASGIClient object at 0x786ef45c8bc0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef45c9fd0>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-497/test_hard_delete_cleans_disk_r0')

    def test_hard_delete_cleans_disk_results(client, monkeypatch, tmp_path) -> None:
        """Hard delete cleans up the results file on disk."""
        import app.main as main_mod

>       job_id = _create_job_in_store(client)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_job_lifecycle.py:245:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

client = <tests.conftest.LocalASGIClient object at 0x786ef45c8bc0>
name = 'lifecycle-test'

    def _create_job_in_store(client, name: str = "lifecycle-test") -> str:
        """POST a fresh manual-mode job and return its ID."""
        payload = {
            "name": name,
            "mode": "manual",
            "urls": ["https://example.com"],
            "schema_fields": [{"name": "company_name", "field_type": "string"}],
        }
        resp = client.post("/api/jobs", json=payload)
>       assert resp.status_code == 200, f"Failed to create job: {resp.text}"
E       AssertionError: Failed to create job: {"detail":"Plan limit exceeded for job_created. Current: 10, Limit: 10 (monthly). Upgrade your plan to continue."}
E       assert 429 == 200
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_job_lifecycle.py:34: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_________________________ TestOWASPTop10.test_a10_ssrf _________________________

self = <tests.test_owasp.TestOWASPTop10 object at 0x786efc50eff0>
client = <tests.conftest.LocalASGIClient object at 0x786ef44114c0>
auth_headers = {}

    def test_a10_ssrf(self, client: TestClient, auth_headers: dict):
        """A10:2021 - Server-Side Request Forgery."""
        # Test SSRF protection
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "SSRF Test",
                "urls": ["http://169.254.169.254/latest/meta-data/"],
            },
        )
        # Should reject internal URLs
>       assert response.status_code in (400, 422)
E       assert 429 in (400, 422)
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_owasp.py:116: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
___________________ TestInputValidation.test_path_traversal ____________________

self = <tests.test_owasp.TestInputValidation object at 0x786efc6e6630>
client = <tests.conftest.LocalASGIClient object at 0x786efd19de20>
auth_headers = {}

    def test_path_traversal(self, client: TestClient, auth_headers: dict):
        """Test path traversal prevention."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["file:///etc/passwd"],
            },
        )
        # Should reject file:// URLs
>       assert response.status_code in (400, 422)
E       assert 429 in (400, 422)
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_owasp.py:195: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
___________________ TestApiKeyManagement.test_create_api_key ___________________
  + Exception Group Traceback (most recent call last):
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 81, in collapse_excgroups
  |     yield
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 192, in __call__
  |     async with anyio.create_task_group() as task_group:
  |   File "/home/harshit/.local/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 799, in __aexit__
  |     raise BaseExceptionGroup(
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | Traceback (most recent call last):
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 353, in from_call
    |     result: TResult | None = func()
    |                              ^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 245, in <lambda>
    |     lambda: runtest_hook(item=item, **kwds),
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/logging.py", line 850, in pytest_runtest_call
    |     yield
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/capture.py", line 900, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/skipping.py", line 268, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 179, in pytest_runtest_call
    |     item.runtest()
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 1720, in runtest
    |     self.ihook.pytest_pyfunc_call(pyfuncitem=self)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 166, in pytest_pyfunc_call
    |     result = testfunction(**testargs)
    |              ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 11, in test_create_api_key
    |     signup = client.post(
    |              ^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    |     return self.request("POST", url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    |     return self._loop.run_until_complete(self._request(method, url, **kwargs))
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    |     return future.result()
    |            ^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    |     return await client.request(method, url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    |     return await self.send(request, auth=auth, follow_redirects=follow_redirects)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    |     response = await self._send_handling_auth(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    |     response = await self._send_handling_redirects(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    |     response = await self._send_single_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    |     response = await transport.handle_async_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    |     await super().__call__(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    |     await self.app(scope, receive, _send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    |     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    |     await route.handle(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    |     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    |     response = await f(request)
    |                ^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    |     raw_response = await run_endpoint_function(
    |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    |     return await dependant.call(**values)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    |     result = svc.signup(
    |              ^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    |     if self.store.get_user_by_email(email_normalized) is not None:
    |        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    |     row = conn.execute(
    |           ^^^^^^^^^^^^^
    | sqlite3.OperationalError: no such table: users
    +------------------------------------

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 11, in test_create_api_key
    signup = client.post(
             ^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    response = await self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    response = await self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    await super().__call__(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    result = svc.signup(
             ^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    row = conn.execute(
          ^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: users

The above exception was the direct cause of the following exception:

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x786efc13e990>
client = <tests.conftest.LocalASGIClient object at 0x786ef57a1c10>

    def test_create_api_key(self, client: TestClient):
        # Sign up to get user + org + project
>       signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-apikeys@example.com",
                "password": "password123",
                "display_name": "API Key Test",
            },
        )

backend/tests/test_saas_api_keys.py:[REDACTED]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
backend/tests/conftest.py:549: in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/tests/conftest.py:543: in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.12/asyncio/base_events.py:687: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
backend/tests/conftest.py:540: in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1540: in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1629: in send
    response = await self._send_handling_auth(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1657: in _send_handling_auth
    response = await self._send_handling_redirects(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1694: in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1730: in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_transports/asgi.py:170: in handle_async_request
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/applications.py:1159: in __call__
    await super().__call__(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/applications.py:90: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:186: in __call__
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:164: in __call__
    await self.app(scope, receive, _send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:212: in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/rate_limiter.py:823: in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:144: in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:124: in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:253: in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/cors.py:88: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py:63: in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py:18: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:660: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:680: in app
    await route.handle(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:276: in handle
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:134: in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:120: in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:674: in app
    raw_response = await run_endpoint_function(
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:328: in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/saas/router.py:173: in signup
    result = svc.signup(
backend/app/saas/service.py:208: in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <app.saas.identity_store.SQLiteIdentityStore object at 0x786ef43ac3b0>
email = 'test-apikeys@example.com'

    def get_user_by_email(self, email: str) -> User | None:
        if not email:
            return None
        with self._lock, self._connect() as conn:
>           row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email.strip(),),
            ).fetchone()
E           sqlite3.OperationalError: no such table: users

backend/app/saas/identity_store.py:375: OperationalError
___________________ TestApiKeyManagement.test_list_api_keys ____________________
  + Exception Group Traceback (most recent call last):
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 81, in collapse_excgroups
  |     yield
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 192, in __call__
  |     async with anyio.create_task_group() as task_group:
  |   File "/home/harshit/.local/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 799, in __aexit__
  |     raise BaseExceptionGroup(
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | Traceback (most recent call last):
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 353, in from_call
    |     result: TResult | None = func()
    |                              ^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 245, in <lambda>
    |     lambda: runtest_hook(item=item, **kwds),
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/logging.py", line 850, in pytest_runtest_call
    |     yield
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/capture.py", line 900, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/skipping.py", line 268, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 179, in pytest_runtest_call
    |     item.runtest()
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 1720, in runtest
    |     self.ihook.pytest_pyfunc_call(pyfuncitem=self)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 166, in pytest_pyfunc_call
    |     result = testfunction(**testargs)
    |              ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 35, in test_list_api_keys
    |     signup = client.post(
    |              ^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    |     return self.request("POST", url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    |     return self._loop.run_until_complete(self._request(method, url, **kwargs))
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    |     return future.result()
    |            ^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    |     return await client.request(method, url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    |     return await self.send(request, auth=auth, follow_redirects=follow_redirects)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    |     response = await self._send_handling_auth(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    |     response = await self._send_handling_redirects(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    |     response = await self._send_single_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    |     response = await transport.handle_async_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    |     await super().__call__(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    |     await self.app(scope, receive, _send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    |     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    |     await route.handle(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    |     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    |     response = await f(request)
    |                ^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    |     raw_response = await run_endpoint_function(
    |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    |     return await dependant.call(**values)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    |     result = svc.signup(
    |              ^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    |     if self.store.get_user_by_email(email_normalized) is not None:
    |        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    |     row = conn.execute(
    |           ^^^^^^^^^^^^^
    | sqlite3.OperationalError: no such table: users
    +------------------------------------

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 35, in test_list_api_keys
    signup = client.post(
             ^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    response = await self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    response = await self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    await super().__call__(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    result = svc.signup(
             ^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    row = conn.execute(
          ^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: users

The above exception was the direct cause of the following exception:

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x786efc13e0f0>
client = <tests.conftest.LocalASGIClient object at 0x786ef7065dc0>

    def test_list_api_keys(self, client: TestClient):
>       signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-list@example.com",
                "password": "password123",
            },
        )

backend/tests/test_saas_api_keys.py:[REDACTED]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
backend/tests/conftest.py:549: in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/tests/conftest.py:543: in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.12/asyncio/base_events.py:687: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
backend/tests/conftest.py:540: in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1540: in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1629: in send
    response = await self._send_handling_auth(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1657: in _send_handling_auth
    response = await self._send_handling_redirects(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1694: in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1730: in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_transports/asgi.py:170: in handle_async_request
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/applications.py:1159: in __call__
    await super().__call__(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/applications.py:90: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:186: in __call__
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:164: in __call__
    await self.app(scope, receive, _send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:212: in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/rate_limiter.py:823: in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:144: in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:124: in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:253: in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/cors.py:88: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py:63: in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py:18: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:660: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:680: in app
    await route.handle(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:276: in handle
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:134: in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:120: in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:674: in app
    raw_response = await run_endpoint_function(
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:328: in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/saas/router.py:173: in signup
    result = svc.signup(
backend/app/saas/service.py:208: in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <app.saas.identity_store.SQLiteIdentityStore object at 0x786ef43ac3b0>
email = 'test-list@example.com'

    def get_user_by_email(self, email: str) -> User | None:
        if not email:
            return None
        with self._lock, self._connect() as conn:
>           row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email.strip(),),
            ).fetchone()
E           sqlite3.OperationalError: no such table: users

backend/app/saas/identity_store.py:375: OperationalError
___________________ TestApiKeyManagement.test_revoke_api_key ___________________
  + Exception Group Traceback (most recent call last):
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 81, in collapse_excgroups
  |     yield
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 192, in __call__
  |     async with anyio.create_task_group() as task_group:
  |   File "/home/harshit/.local/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 799, in __aexit__
  |     raise BaseExceptionGroup(
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | Traceback (most recent call last):
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 353, in from_call
    |     result: TResult | None = func()
    |                              ^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 245, in <lambda>
    |     lambda: runtest_hook(item=item, **kwds),
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/logging.py", line 850, in pytest_runtest_call
    |     yield
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/capture.py", line 900, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/skipping.py", line 268, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 179, in pytest_runtest_call
    |     item.runtest()
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 1720, in runtest
    |     self.ihook.pytest_pyfunc_call(pyfuncitem=self)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 166, in pytest_pyfunc_call
    |     result = testfunction(**testargs)
    |              ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 57, in test_revoke_api_key
    |     signup = client.post(
    |              ^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    |     return self.request("POST", url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    |     return self._loop.run_until_complete(self._request(method, url, **kwargs))
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    |     return future.result()
    |            ^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    |     return await client.request(method, url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    |     return await self.send(request, auth=auth, follow_redirects=follow_redirects)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    |     response = await self._send_handling_auth(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    |     response = await self._send_handling_redirects(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    |     response = await self._send_single_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    |     response = await transport.handle_async_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    |     await super().__call__(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    |     await self.app(scope, receive, _send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    |     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    |     await route.handle(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    |     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    |     response = await f(request)
    |                ^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    |     raw_response = await run_endpoint_function(
    |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    |     return await dependant.call(**values)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    |     result = svc.signup(
    |              ^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    |     if self.store.get_user_by_email(email_normalized) is not None:
    |        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    |     row = conn.execute(
    |           ^^^^^^^^^^^^^
    | sqlite3.OperationalError: no such table: users
    +------------------------------------

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 57, in test_revoke_api_key
    signup = client.post(
             ^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    response = await self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    response = await self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    await super().__call__(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    result = svc.signup(
             ^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    row = conn.execute(
          ^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: users

The above exception was the direct cause of the following exception:

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x786efc13d850>
client = <tests.conftest.LocalASGIClient object at 0x786efc3699d0>

    def test_revoke_api_key(self, client: TestClient):
>       signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-revoke@example.com",
                "password": "password123",
            },
        )

backend/tests/test_saas_api_keys.py:[REDACTED]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
backend/tests/conftest.py:549: in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/tests/conftest.py:543: in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.12/asyncio/base_events.py:687: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
backend/tests/conftest.py:540: in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1540: in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1629: in send
    response = await self._send_handling_auth(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1657: in _send_handling_auth
    response = await self._send_handling_redirects(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1694: in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1730: in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_transports/asgi.py:170: in handle_async_request
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/applications.py:1159: in __call__
    await super().__call__(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/applications.py:90: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:186: in __call__
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:164: in __call__
    await self.app(scope, receive, _send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:212: in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/rate_limiter.py:823: in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:144: in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:124: in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:253: in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/cors.py:88: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py:63: in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py:18: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:660: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:680: in app
    await route.handle(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:276: in handle
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:134: in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:120: in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:674: in app
    raw_response = await run_endpoint_function(
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:328: in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/saas/router.py:173: in signup
    result = svc.signup(
backend/app/saas/service.py:208: in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <app.saas.identity_store.SQLiteIdentityStore object at 0x786ef43ac3b0>
email = 'test-revoke@example.com'

    def get_user_by_email(self, email: str) -> User | None:
        if not email:
            return None
        with self._lock, self._connect() as conn:
>           row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email.strip(),),
            ).fetchone()
E           sqlite3.OperationalError: no such table: users

backend/app/saas/identity_store.py:375: OperationalError
____________ TestApiKeyManagement.test_cross_project_access_denied _____________
  + Exception Group Traceback (most recent call last):
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 81, in collapse_excgroups
  |     yield
  |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 192, in __call__
  |     async with anyio.create_task_group() as task_group:
  |   File "/home/harshit/.local/lib/python3.12/site-packages/anyio/_backends/_asyncio.py", line 799, in __aexit__
  |     raise BaseExceptionGroup(
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    | Traceback (most recent call last):
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 353, in from_call
    |     result: TResult | None = func()
    |                              ^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 245, in <lambda>
    |     lambda: runtest_hook(item=item, **kwds),
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/logging.py", line 850, in pytest_runtest_call
    |     yield
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/capture.py", line 900, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/skipping.py", line 268, in pytest_runtest_call
    |     return (yield)
    |             ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/runner.py", line 179, in pytest_runtest_call
    |     item.runtest()
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 1720, in runtest
    |     self.ihook.pytest_pyfunc_call(pyfuncitem=self)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    |     return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    |     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
    |     raise exception
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 139, in _multicall
    |     teardown.throw(exception)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 53, in run_old_style_hookwrapper
    |     return result.get_result()
    |            ^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_result.py", line 103, in get_result
    |     raise exc.with_traceback(tb)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 38, in run_old_style_hookwrapper
    |     res = yield
    |           ^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    |     res = hook_impl.function(*args)
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/python.py", line 166, in pytest_pyfunc_call
    |     result = testfunction(**testargs)
    |              ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 83, in test_cross_project_access_denied
    |     signup1 = client.post(
    |               ^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    |     return self.request("POST", url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    |     return self._loop.run_until_complete(self._request(method, url, **kwargs))
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    |     return future.result()
    |            ^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    |     return await client.request(method, url, **kwargs)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    |     return await self.send(request, auth=auth, follow_redirects=follow_redirects)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    |     response = await self._send_handling_auth(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    |     response = await self._send_handling_redirects(
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    |     response = await self._send_single_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    |     response = await transport.handle_async_request(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    |     await super().__call__(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    |     await self.app(scope, receive, _send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    |     return await call_next(request)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    |     with recv_stream, send_stream, collapse_excgroups():
    |   File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    |     self.gen.throw(value)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    |     response = await self.dispatch_func(request, call_next)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    |     response = await call_next(request)
    |                ^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    |     raise app_exc from app_exc.__cause__ or app_exc.__context__
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    |     await self.app(scope, receive_or_disconnect, send_no_error)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    |     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    |     await self.middleware_stack(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    |     await route.handle(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    |     await self.app(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    |     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    |     raise exc
    |   File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    |     await app(scope, receive, sender)
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    |     response = await f(request)
    |                ^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    |     raw_response = await run_endpoint_function(
    |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    |     return await dependant.call(**values)
    |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    |     result = svc.signup(
    |              ^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    |     if self.store.get_user_by_email(email_normalized) is not None:
    |        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |   File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    |     row = conn.execute(
    |           ^^^^^^^^^^^^^
    | sqlite3.OperationalError: no such table: users
    +------------------------------------

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/test_saas_api_keys.py", line 83, in test_cross_project_access_denied
    signup1 = client.post(
              ^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 549, in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 543, in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py", line 540, in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1540, in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1629, in send
    response = await self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    response = await self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_client.py", line 1730, in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/httpx/_transports/asgi.py", line 170, in handle_async_request
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/applications.py", line 1159, in __call__
    await super().__call__(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 186, in __call__
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 212, in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/rate_limiter.py", line 823, in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 144, in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 124, in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 191, in __call__
    with recv_stream, send_stream, collapse_excgroups():
  File "/usr/lib/python3.12/contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_utils.py", line 87, in collapse_excgroups
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 193, in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/middlewares.py", line 253, in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 168, in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/base.py", line 144, in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/cors.py", line 88, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 134, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/harshit/.local/lib/python3.12/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 120, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 674, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/.local/lib/python3.12/site-packages/fastapi/routing.py", line 328, in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 173, in signup
    result = svc.signup(
             ^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/service.py", line 208, in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/identity_store.py", line 375, in get_user_by_email
    row = conn.execute(
          ^^^^^^^^^^^^^
sqlite3.OperationalError: no such table: users

The above exception was the direct cause of the following exception:

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x786efc13c770>
client = <tests.conftest.LocalASGIClient object at 0x786ee733d190>

    def test_cross_project_access_denied(self, client: TestClient):
        # Create two users with separate projects
>       signup1 = client.post(
            "/api/saas/signup",
            json={
                "email": "user1@example.com",
                "password": "password123",
            },
        )

backend/tests/test_saas_api_keys.py:[REDACTED]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
backend/tests/conftest.py:549: in post
    return self.request("POST", url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/tests/conftest.py:543: in request
    return self._loop.run_until_complete(self._request(method, url, **kwargs))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.12/asyncio/base_events.py:687: in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
backend/tests/conftest.py:540: in _request
    return await client.request(method, url, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1540: in request
    return await self.send(request, auth=auth, follow_redirects=follow_redirects)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1629: in send
    response = await self._send_handling_auth(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1657: in _send_handling_auth
    response = await self._send_handling_redirects(
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1694: in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_client.py:1730: in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/httpx/_transports/asgi.py:170: in handle_async_request
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/applications.py:1159: in __call__
    await super().__call__(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/applications.py:90: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:186: in __call__
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/errors.py:164: in __call__
    await self.app(scope, receive, _send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:212: in latency_tracking_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/rate_limiter.py:823: in middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:144: in api_key_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:124: in body_size_middleware
    return await call_next(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:191: in __call__
    with recv_stream, send_stream, collapse_excgroups():
/usr/lib/python3.12/contextlib.py:158: in __exit__
    self.gen.throw(value)
../../../../.local/lib/python3.12/site-packages/starlette/_utils.py:87: in collapse_excgroups
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:193: in __call__
    response = await self.dispatch_func(request, call_next)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/middlewares.py:253: in csp_report_only_middleware
    response = await call_next(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:168: in call_next
    raise app_exc from app_exc.__cause__ or app_exc.__context__
../../../../.local/lib/python3.12/site-packages/starlette/middleware/base.py:144: in coro
    await self.app(scope, receive_or_disconnect, send_no_error)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/cors.py:88: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/middleware/exceptions.py:63: in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/middleware/asyncexitstack.py:18: in __call__
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:660: in __call__
    await self.middleware_stack(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:680: in app
    await route.handle(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/routing.py:276: in handle
    await self.app(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:134: in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:53: in wrapped_app
    raise exc
../../../../.local/lib/python3.12/site-packages/starlette/_exception_handler.py:42: in wrapped_app
    await app(scope, receive, sender)
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:120: in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:674: in app
    raw_response = await run_endpoint_function(
../../../../.local/lib/python3.12/site-packages/fastapi/routing.py:328: in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
backend/app/saas/router.py:173: in signup
    result = svc.signup(
backend/app/saas/service.py:208: in signup
    if self.store.get_user_by_email(email_normalized) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <app.saas.identity_store.SQLiteIdentityStore object at 0x786ef43ac3b0>
email = 'user1@example.com'

    def get_user_by_email(self, email: str) -> User | None:
        if not email:
            return None
        with self._lock, self._connect() as conn:
>           row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email.strip(),),
            ).fetchone()
E           sqlite3.OperationalError: no such table: users

backend/app/saas/identity_store.py:375: OperationalError
______________ TestInputValidation.test_sql_injection_in_job_name ______________

self = <tests.test_security.TestInputValidation object at 0x786efc2e6210>
client = <tests.conftest.LocalASGIClient object at 0x786ee726e0c0>
auth_headers = {}

    def test_sql_injection_in_job_name(self, client: TestClient, auth_headers: dict):
        """Test SQL injection attempts in job name."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "'; DROP TABLE jobs; --",
                "urls": ["https://example.com"],
            },
        )
        # Should either reject or sanitize the input
>       assert response.status_code in (400, 422, 200)
E       assert 429 in (400, 422, 200)
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_security.py:33: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
________________ TestInputValidation.test_path_traversal_in_url ________________

self = <tests.test_security.TestInputValidation object at 0x786efc19cd10>
client = <tests.conftest.LocalASGIClient object at 0x786ef5f61d30>
auth_headers = {}

    def test_path_traversal_in_url(self, client: TestClient, auth_headers: dict):
        """Test path traversal attempts in URL."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["file:///etc/passwd"],
            },
        )
        # Should reject file:// URLs
>       assert response.status_code in (400, 422)
E       assert 429 in (400, 422)
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_security.py:65: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_________________ TestInputValidation.test_invalid_url_format __________________

self = <tests.test_security.TestInputValidation object at 0x786efc19dd30>
client = <tests.conftest.LocalASGIClient object at 0x786ef5f632f0>
auth_headers = {}

    def test_invalid_url_format(self, client: TestClient, auth_headers: dict):
        """Test invalid URL format handling."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["not-a-url"],
            },
        )
>       assert response.status_code in (400, 422)
E       assert 429 in (400, 422)
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_security.py:77: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
___________________ TestInputValidation.test_empty_url_list ____________________

self = <tests.test_security.TestInputValidation object at 0x786efc2e4500>
client = <tests.conftest.LocalASGIClient object at 0x786ee74e8e60>
auth_headers = {}

    def test_empty_url_list(self, client: TestClient, auth_headers: dict):
        """Test empty URL list handling."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": [],
            },
        )
>       assert response.status_code in (400, 422)
E       assert 429 in (400, 422)
E        +  where 429 = <Response [429 Too Many Requests]>.status_code

backend/tests/test_security.py:89: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  app.plan_enforcer:plan_enforcer.py:133 Plan limit exceeded: user=dev-admin tier=free type=job_created current=10 limit=10
_____________ test_v5_to_v6_migration_preserves_worker_heartbeats ______________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x786ef7d76840>
tmp_db = PosixPath('/tmp/pytest-of-harshit/pytest-497/test_v5_to_v6_migration_preser0/test.db')

    def test_v5_to_v6_migration_preserves_worker_heartbeats(monkeypatch, tmp_db) -> None:
        """Migration from v5 to v6 should rebuild worker_heartbeats with composite PK."""
        monkeypatch.setattr("app.job_store._get_db_path", lambda: tmp_db)

        # Create stub tables that _run_migrations expects at hot-path index creation
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, name TEXT, status TEXT DEFAULT '', created_at TEXT DEFAULT '')",
        )
        conn.execute("CREATE TABLE IF NOT EXISTS recycle_bin (id TEXT PRIMARY KEY, name TEXT, created_at TEXT DEFAULT '')")
        # Create a v5-style worker_heartbeats table (single PK on worker_id)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS worker_heartbeats (
                worker_id TEXT PRIMARY KEY,
                last_heartbeat TEXT NOT NULL,
                hostname TEXT NOT NULL DEFAULT '',
                pid INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL DEFAULT ''
            )
        """)
        # Insert one row per worker_id (v5 schema enforced single PK on worker_id)
        conn.execute(
            "INSERT INTO worker_heartbeats (worker_id, last_heartbeat, hostname, pid, started_at) VALUES (?, ?, ?, ?, ?)",
            ("worker-a", "2026-06-09T10:00:00", "host1", 1001, "2026-06-09T09:00:00"),
        )
        conn.execute(
            "INSERT INTO worker_heartbeats (worker_id, last_heartbeat, hostname, pid, started_at) VALUES (?, ?, ?, ?, ?)",
            ("worker-b", "2026-06-09T10:02:00", "host2", 2001, "2026-06-09T09:02:00"),
        )
        # Create and set schema_version to 5 to simulate v5 schema
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version (version) VALUES (5)")
        conn.commit()
        conn.close()

        # Now run the full migration (v5 -> v6)
        from app.job_store import _run_migrations

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        _run_migrations(conn)

        # Verify schema_version is now 8 (v8 adds org_id/project_id columns)
        ver_row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
>       assert ver_row[0] == 8, f"Expected schema version 8, got {ver_row[0]}"
E       AssertionError: Expected schema version 8, got 9
E       assert 9 == 8

backend/tests/test_storage_migrations.py:273: AssertionError
=========================== short test summary info ============================
FAILED backend/tests/test_api_worker_integration.py::TestWorkerPicksQueuedJob::test_worker_picks_queued_job_and_updates_repo
FAILED backend/tests/test_api_worker_integration.py::TestRealWorkerHandler::test_real_worker_handler_executes_via_api
FAILED backend/tests/test_idempotency_keys.py::TestIdempotencyHappyPath::test_repeated_key_returns_same_job_id
FAILED backend/tests/test_idempotency_keys.py::TestIdempotencyHappyPath::test_repeated_key_with_different_payload_returns_409
FAILED backend/tests/test_idempotency_keys.py::TestIdempotencyHappyPath::test_different_keys_create_different_jobs
FAILED backend/tests/test_idempotency_keys.py::TestIdempotencyHappyPath::test_no_header_means_no_replay
FAILED backend/tests/test_idempotency_keys.py::TestIdempotencyValidation::test_overlong_key_is_rejected
FAILED backend/tests/test_job_lifecycle.py::test_double_cancel_terminal_job_returns_early
FAILED backend/tests/test_job_lifecycle.py::test_cancel_active_job_sets_request_flag
FAILED backend/tests/test_job_lifecycle.py::test_cancel_pending_job_auto_cancels
FAILED backend/tests/test_job_lifecycle.py::test_delete_terminal_job_moves_to_recycle_bin
FAILED backend/tests/test_job_lifecycle.py::test_restore_job_from_recycle_bin
FAILED backend/tests/test_job_lifecycle.py::test_list_recycle_bin_shows_moved_jobs
FAILED backend/tests/test_job_lifecycle.py::test_restore_and_re_delete_round_trip
FAILED backend/tests/test_job_lifecycle.py::test_hard_delete_removes_permanently
FAILED backend/tests/test_job_lifecycle.py::test_hard_delete_cleans_disk_results
FAILED backend/tests/test_owasp.py::TestOWASPTop10::test_a10_ssrf - assert 42...
FAILED backend/tests/test_owasp.py::TestInputValidation::test_path_traversal
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_security.py::TestInputValidation::test_sql_injection_in_job_name
FAILED backend/tests/test_security.py::TestInputValidation::test_path_traversal_in_url
FAILED backend/tests/test_security.py::TestInputValidation::test_invalid_url_format
FAILED backend/tests/test_security.py::TestInputValidation::test_empty_url_list
FAILED backend/tests/test_storage_migrations.py::test_v5_to_v6_migration_preserves_worker_heartbeats

```

## stderr

```text

```
