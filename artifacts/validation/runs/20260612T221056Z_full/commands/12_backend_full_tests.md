# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T22:11:11.322129+00:00
- end_time: 2026-06-12T22:14:40.807619+00:00
- duration_seconds: 209.49
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: true

## stdout

```text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
..........F............................................................. [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................................................ [ 18%]
..................s..................................................... [ 20%]
........................................................................ [ 22%]
........................................................................ [ 24%]
................F..F.................................................... [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
.............................................ssssssss................... [ 32%]
........................................................................ [ 34%]
......................................s.................s............... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
....................................................ssssssssssssssssssss [ 50%]
ss...........................ss......................................... [ 52%]
............................ss......................................F..F [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
...........................................sssssssssssss................ [ 60%]
...................s.................................................... [ 62%]
........................................................................ [ 64%]
.......................FFFFF.................FFFF....................... [ 66%]
........................................................................ [ 68%]
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
___________________ TestAuthProfileModel.test_create_profile ___________________

self = <tests.test_auth_profiles.TestAuthProfileModel object at 0x7cfd951ee1b0>

    def test_create_profile(self):
        p = AuthProfile(name="Login for example.com", domain="example.com")
        assert p.name == "Login for example.com"
        assert p.domain == "example.com"
>       assert p.status == AuthProfileStatus.ACTIVE
E       AssertionError: assert <AuthProfileS...ending_login'> == <AuthProfileS...IVE: 'active'>
E
E         - active
E         + pending_login

backend/tests/test_auth_profiles.py:16: AssertionError
_____________ TestFailureExplainer.test_detect_selector_not_found ______________

self = <tests.test_extraction_depth.TestFailureExplainer object at 0x7cfd94b25760>

    def test_detect_selector_not_found(self):
        explanation = detect_failure(selector_found=False, records_found=0)
>       assert explanation.failure_type == "no_records_found"
E       AssertionError: assert 'selector_not_found' == 'no_records_found'
E
E         - no_records_found
E         + selector_not_found

backend/tests/test_extraction_depth.py:185: AssertionError
____________ TestFailureExplainer.test_explain_failure_unknown_type ____________

self = <tests.test_extraction_depth.TestFailureExplainer object at 0x7cfd94b26450>

    def test_explain_failure_unknown_type(self):
        explanation = explain_failure("nonexistent_type")
>       assert explanation.failure_type == "unknown_error"
E       AssertionError: assert 'nonexistent_type' == 'unknown_error'
E
E         - unknown_error
E         + nonexistent_type

backend/tests/test_extraction_depth.py:199: AssertionError
_____________________________ test_pyflakes_clean ______________________________

    def test_pyflakes_clean() -> None:
        """Run pyflakes programmatically over backend/app and backend/tests and assert no warnings or errors."""
        # Resolve the absolute path to the backend directory dynamically
        backend_dir = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", "app", "tests"],
            cwd=str(backend_dir),
            text=True,
            capture_output=True,
        )

>       assert result.returncode == 0, f"Pyflakes validation failed with warnings/errors:\n{result.stdout}\n{result.stderr}"
E       AssertionError: Pyflakes validation failed with warnings/errors:
E         app/plan_enforcer.py:17:1: 'functools.lru_cache' imported but unused
E         app/plan_enforcer.py:22:1: 'app.utils.rbac.AuthContext' imported but unused
E
E
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/usr/bin/python3', '-m', 'pyflakes', 'app', 'tests'], returncode=1, stdout="app/plan_enforcer...._cache' imported but unused\napp/plan_enforcer.py:22:1: 'app.utils.rbac.AuthContext' imported but unused\n", stderr='').returncode

backend/tests/test_pyflakes_fixes.py:20: AssertionError
_____________________ test_pytest_timeout_plugin_is_loaded _____________________

    def test_pytest_timeout_plugin_is_loaded() -> None:
        """pytest-timeout's plugin is registered at pytest startup."""
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--markers"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
>       assert proc.returncode == 0, f"pytest --markers failed: {proc.stderr}"
E       AssertionError: pytest --markers failed: ImportError while loading conftest '/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py'.
E         backend/tests/conftest.py:251: in <module>
E             import app.main
E         backend/app/main.py:44: in <module>
E             from app.routers.jobs import create_jobs_router
E         backend/app/routers/jobs.py:22: in <module>
E             from app.routers.jobs_write import register_jobs_write_routes
E         backend/app/routers/jobs_write.py:51: in <module>
E             from app.plan_enforcer import require_plan_limit
E         backend/app/plan_enforcer.py:25: in <module>
E             logger = logging.get(__name__)
E                      ^^^^^^^^^^^
E         E   AttributeError: module 'logging' has no attribute 'get'
E
E       assert 4 == 0
E        +  where 4 = CompletedProcess(args=['/usr/bin/python3', '-m', 'pytest', '--markers'], returncode=4, stdout='', stderr="ImportError ...gger = logging.get(__name__)\n             ^^^^^^^^^^^\nE   AttributeError: module 'logging' has no attribute 'get'\n").returncode

backend/tests/test_pytest_timeout.py:66: AssertionError
_____________________ test_split_script_runs_without_args ______________________

    def test_split_script_runs_without_args() -> None:
        """The script can be imported and run with no flags (side-effect free)."""
        stdout, stderr, rc = _run_split()
>       assert rc == 0, f"split script failed: {stderr}"
E       AssertionError: split script failed: Failed to import app.main:
E         Traceback (most recent call last):
E           File "<string>", line 1, in <module>
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/main.py", line 44, in <module>
E             from app.routers.jobs import create_jobs_router
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs.py", line 22, in <module>
E             from app.routers.jobs_write import register_jobs_write_routes
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs_write.py", line 51, in <module>
E             from app.plan_enforcer import require_plan_limit
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/plan_enforcer.py", line 25, in <module>
E             logger = logging.get(__name__)
E                      ^^^^^^^^^^^
E         AttributeError: module 'logging' has no attribute 'get'
E
E
E       assert 2 == 0

backend/tests/test_route_inventory_split.py:50: AssertionError
_________________ test_stable_is_strict_subset_of_experimental _________________

    def test_stable_is_strict_subset_of_experimental() -> None:
        """The experimental set is a strict superset of the stable set.

        If this ever fails (stable has a route the experimental set does
        not, or both sets are equal), the route inventory gate is broken
        and the docs would mislead operators in production.
        """
        _stdout, stderr, _ = _run_split()
        m = re.search(r"stable=(\d+) experimental=(\d+) diff=(\d+)", stderr)
>       assert m, f"could not parse counts from {stderr!r}"
E       AssertionError: could not parse counts from 'Failed to import app.main:\nTraceback (most recent call last):\n  File "<string>", line 1, in <module>\n  File "/home/harshit/Documents/Work/Money/scraper/backend/app/main.py", line 44, in <module>\n    from app.routers.jobs import create_jobs_router\n  File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs.py", line 22, in <module>\n    from app.routers.jobs_write import register_jobs_write_routes\n  File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs_write.py", line 51, in <module>\n    from app.plan_enforcer import require_plan_limit\n  File "/home/harshit/Documents/Work/Money/scraper/backend/app/plan_enforcer.py", line 25, in <module>\n    logger = logging.get(__name__)\n             ^^^^^^^^^^^\nAttributeError: module \'logging\' has no attribute \'get\'\n\n'
E       assert None

backend/tests/test_route_inventory_split.py:69: AssertionError
____________________ test_split_writes_to_docs_when_invoked ____________________

    def test_split_writes_to_docs_when_invoked() -> None:
        """The ``--write`` flag persists the generated Markdown files."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--write"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
>       assert proc.returncode == 0, f"--write failed: {proc.stderr}"
E       AssertionError: --write failed: Failed to import app.main:
E         Traceback (most recent call last):
E           File "<string>", line 1, in <module>
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/main.py", line 44, in <module>
E             from app.routers.jobs import create_jobs_router
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs.py", line 22, in <module>
E             from app.routers.jobs_write import register_jobs_write_routes
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs_write.py", line 51, in <module>
E             from app.plan_enforcer import require_plan_limit
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/plan_enforcer.py", line 25, in <module>
E             logger = logging.get(__name__)
E                      ^^^^^^^^^^^
E         AttributeError: module 'logging' has no attribute 'get'
E
E
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/usr/bin/python3', '/home/harshit/Documents/Work/Money/scraper/scripts/route_inventory_split.p...er = logging.get(__name__)\n             ^^^^^^^^^^^\nAttributeError: module \'logging\' has no attribute \'get\'\n\n').returncode

backend/tests/test_route_inventory_split.py:89: AssertionError
________________ test_each_doc_has_the_expected_section_header _________________

    def test_each_doc_has_the_expected_section_header() -> None:
        """Each generated Markdown file must carry its identifying header."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--write"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
>       assert proc.returncode == 0
E       AssertionError: assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/usr/bin/python3', '/home/harshit/Documents/Work/Money/scraper/scripts/route_inventory_split.p...er = logging.get(__name__)\n             ^^^^^^^^^^^\nAttributeError: module \'logging\' has no attribute \'get\'\n\n').returncode

backend/tests/test_route_inventory_split.py:108: AssertionError
_____________________ test_split_runs_under_global_timeout _____________________

    @pytest.mark.timeout(60)
    def test_split_runs_under_global_timeout() -> None:
        """The split script must complete well under the global 30s pytest timeout.

        If this test times out, the inventory import path picked up a
        network call (DNS, DB) and we need to fix the isolation before
        merging the Phase 0 work.
        """
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--write"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
>       assert proc.returncode == 0, f"split --write exceeded 25s or failed: {proc.stderr}"
E       AssertionError: split --write exceeded 25s or failed: Failed to import app.main:
E         Traceback (most recent call last):
E           File "<string>", line 1, in <module>
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/main.py", line 44, in <module>
E             from app.routers.jobs import create_jobs_router
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs.py", line 22, in <module>
E             from app.routers.jobs_write import register_jobs_write_routes
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/routers/jobs_write.py", line 51, in <module>
E             from app.plan_enforcer import require_plan_limit
E           File "/home/harshit/Documents/Work/Money/scraper/backend/app/plan_enforcer.py", line 25, in <module>
E             logger = logging.get(__name__)
E                      ^^^^^^^^^^^
E         AttributeError: module 'logging' has no attribute 'get'
E
E
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/usr/bin/python3', '/home/harshit/Documents/Work/Money/scraper/scripts/route_inventory_split.p...er = logging.get(__name__)\n             ^^^^^^^^^^^\nAttributeError: module \'logging\' has no attribute \'get\'\n\n').returncode

backend/tests/test_route_inventory_split.py:130: AssertionError
___________________ TestApiKeyManagement.test_create_api_key ___________________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7cfd9413e3f0>
client = <tests.conftest.LocalASGIClient object at 0x7cfd7ff99490>

    def test_create_api_key(self, client: TestClient):
        # Sign up to get user + org + project
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-apikeys@example.com",
                "password": "password123",
                "display_name": "API Key Test",
            },
        )
>       assert signup.status_code == 201
E       assert 409 == 201
E        +  where 409 = <Response [409 Conflict]>.status_code

backend/tests/test_saas_api_keys.py:[REDACTED] AssertionError
___________________ TestApiKeyManagement.test_list_api_keys ____________________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7cfd9413e840>
client = <tests.conftest.LocalASGIClient object at 0x7cfd8f263740>

    def test_list_api_keys(self, client: TestClient):
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-list@example.com",
                "password": "password123",
            },
        )
>       project_id = signup.json()["project_id"]
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'project_id'

backend/tests/test_saas_api_keys.py:[REDACTED] KeyError
___________________ TestApiKeyManagement.test_revoke_api_key ___________________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7cfd9413ecc0>
client = <tests.conftest.LocalASGIClient object at 0x7cfd8f8c5df0>

    def test_revoke_api_key(self, client: TestClient):
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-revoke@example.com",
                "password": "password123",
            },
        )
>       project_id = signup.json()["project_id"]
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'project_id'

backend/tests/test_saas_api_keys.py:[REDACTED] KeyError
____________ TestApiKeyManagement.test_cross_project_access_denied _____________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7cfd9413f140>
client = <tests.conftest.LocalASGIClient object at 0x7cfd8f8c48f0>

    def test_cross_project_access_denied(self, client: TestClient):
        # Create two users with separate projects
        signup1 = client.post(
            "/api/saas/signup",
            json={
                "email": "user1@example.com",
                "password": "password123",
            },
        )
>       signup1.json()["project_id"]
E       KeyError: 'project_id'

backend/tests/test_saas_api_keys.py:[REDACTED] KeyError
_____________ test_v5_to_v6_migration_preserves_worker_heartbeats ______________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7cfd8d337ce0>
tmp_db = PosixPath('/tmp/pytest-of-harshit/pytest-467/test_v5_to_v6_migration_preser0/test.db')

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
FAILED backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_create_profile
FAILED backend/tests/test_extraction_depth.py::TestFailureExplainer::test_detect_selector_not_found
FAILED backend/tests/test_extraction_depth.py::TestFailureExplainer::test_explain_failure_unknown_type
FAILED backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean - AssertionE...
FAILED backend/tests/test_pytest_timeout.py::test_pytest_timeout_plugin_is_loaded
FAILED backend/tests/test_route_inventory_split.py::test_split_script_runs_without_args
FAILED backend/tests/test_route_inventory_split.py::test_stable_is_strict_subset_of_experimental
FAILED backend/tests/test_route_inventory_split.py::test_split_writes_to_docs_when_invoked
FAILED backend/tests/test_route_inventory_split.py::test_each_doc_has_the_expected_section_header
FAILED backend/tests/test_route_inventory_split.py::test_split_runs_under_global_timeout
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_storage_migrations.py::test_v5_to_v6_migration_preserves_worker_heartbeats

```

## stderr

```text

```
