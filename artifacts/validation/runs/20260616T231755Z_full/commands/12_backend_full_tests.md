# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T23:18:11.628723+00:00
- end_time: 2026-06-16T23:24:59.822192+00:00
- duration_seconds: 408.19
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: true

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
........................................................................ [  5%]
.............................................ss......................... [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 15%]
........................................................................ [ 17%]
................................s....................................... [ 19%]
........................................................................ [ 21%]
........................................................................ [ 23%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
.......ssssssss......................................................... [ 32%]
........................................................................ [ 34%]
s.................s..................................................... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
..............................................................ssssssssss [ 49%]
ssssssssssss...........................ss............................... [ 51%]
..........................................ss............................ [ 53%]
.........+++++++++++++++++++++++++++++++++++ Timeout ++++++++++++++++++++++++++++++++++++
~~~~~~~~~~~~~~ Stack of ThreadPoolExecutor-1_0 (136718516745920) ~~~~~~~~~~~~~~~
  File "/usr/lib/python3.12/threading.py", line 1030, in _bootstrap
    self._bootstrap_inner()
  File "/usr/lib/python3.12/threading.py", line 1073, in _bootstrap_inner
    self.run()
  File "/usr/lib/python3.12/threading.py", line 1010, in run
    self._target(*self._args, **self._kwargs)
  File "/usr/lib/python3.12/concurrent/futures/thread.py", line 89, in _worker
    work_item = work_queue.get(block=True)
~~~~~~~~~~~~~~~ Stack of Thread-1 (run_server) (136718630012608) ~~~~~~~~~~~~~~~
  File "/usr/lib/python3.12/threading.py", line 1030, in _bootstrap
    self._bootstrap_inner()
  File "/usr/lib/python3.12/threading.py", line 1073, in _bootstrap_inner
    self.run()
  File "/usr/lib/python3.12/threading.py", line 1010, in run
    self._target(*self._args, **self._kwargs)
  File "/home/harshit/.local/lib/python3.12/site-packages/pytest_rerunfailures.py", line 505, in run_server
    conn, _ = self.sock.accept()
  File "/usr/lib/python3.12/socket.py", line 295, in accept
    fd, addr = self._accept()
+++++++++++++++++++++++++++++++++++ Timeout ++++++++++++++++++++++++++++++++++++
F....................................................................... [ 55%]
........................................................................ [ 57%]
................................................sssssssssssss........... [ 59%]
........................s............................................... [ 61%]
........................................................................ [ 63%]
..................................................FFF................... [ 65%]
...............................................................ss....... [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 80%]
....................................sssssss............................. [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
...................................s...................ss..sssssssssssss [ 96%]
ssssss.................................................................. [ 98%]
................................................................         [100%]
=================================== FAILURES ===================================
__________ TestFactorySelectsPsycopg3.test_default_driver_is_psycopg2 __________

    def verify_postgres_connectivity() -> dict[str, Any]:
        """Synchronously verify Postgres is reachable before activating the repository.

        Uses a standalone connection (not the shared pool) so the pool is
        never leaked on failure or left open if the caller falls back to SQLite.

        Returns a dict with 'ok': True / False and optional 'error' message.
        """
        try:
            dsn = get_database_url()
>           conn = psycopg2.connect(dsn, connect_timeout=10)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/app/postgres_repository.py:191:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

dsn = 'user=x password=[REDACTED] dbname=z host=h port=5432 connect_timeout=10'
connection_factory = None, cursor_factory = None
kwargs = {'connect_timeout': 10}, kwasync = {}

    def connect(dsn=None, connection_factory=None, cursor_factory=None, **kwargs):
        """
        Create a new database connection.

        The connection parameters can be specified as a string:

            conn = psycopg2.connect("dbname=test user=postgres password=[REDACTED]

        or using a set of keyword arguments:

            conn = psycopg2.connect(database="test", user="postgres", password=[REDACTED]

        Or as a mix of both. The basic connection parameters are:

        - *dbname*: the database name
        - *database*: the database name (only as keyword argument)
        - *user*: user name used to authenticate
        - *password*: password used to authenticate
        - *host*: database host address (defaults to UNIX socket if not provided)
        - *port*: connection port number (defaults to 5432 if not provided)

        Using the *connection_factory* parameter a different class or connections
        factory can be specified. It should be a callable object taking a dsn
        argument.

        Using the *cursor_factory* parameter, a new default cursor factory will be
        used by cursor().

        Using *async*=True an asynchronous connection will be created. *async_* is
        a valid alias (for Python versions where ``async`` is a keyword).

        Any other keyword parameter will be passed to the underlying client
        library: the list of supported parameters depends on the library version.

        """
        kwasync = {}
        if 'async' in kwargs:
            kwasync['async'] = kwargs.pop('async')
        if 'async_' in kwargs:
            kwasync['async_'] = kwargs.pop('async_')

        dsn = _ext.make_dsn(dsn, **kwargs)
>       conn = _connect(dsn, connection_factory=connection_factory, **kwasync)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       psycopg2.OperationalError: could not translate host name "h" to address: Name or service not known

../../../../.local/lib/python3.12/site-packages/psycopg2/__init__.py:122: OperationalError

During handling of the above exception, another exception occurred:

self = <tests.test_psycopg3_repository.TestFactorySelectsPsycopg3 object at 0x7c5843ebeb40>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7c5841ad6cf0>

    def test_default_driver_is_psycopg2(self, monkeypatch) -> None:
        """When no driver is specified, the factory should keep using
        psycopg2 (preserves existing behaviour).
        """
        monkeypatch.delenv("DATAFORGE_PG_DRIVER", raising=False)
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://x:y@h:5432/z")
        # Clear the env to ensure we read from default.
        from app.storage_interface import get_job_repository

        reset_repository()
        try:
            # No DB is running, so we expect a connection error
            # mentioning the psycopg2 driver, not psycopg3.
            with pytest.raises(RuntimeError) as exc:
>               get_job_repository()

backend/tests/test_psycopg3_repository.py:207:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
backend/app/storage_interface.py:994: in get_job_repository
    connectivity = verify_postgres_connectivity()
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    def verify_postgres_connectivity() -> dict[str, Any]:
        """Synchronously verify Postgres is reachable before activating the repository.

        Uses a standalone connection (not the shared pool) so the pool is
        never leaked on failure or left open if the caller falls back to SQLite.

        Returns a dict with 'ok': True / False and optional 'error' message.
        """
        try:
            dsn = get_database_url()
            conn = psycopg2.connect(dsn, connect_timeout=10)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    if result is None:
                        return {"ok": False, "error": "No result from health check query"}
                    val = result[0]
                    return {"ok": val == 1}
            finally:
                conn.close()
        except ImportError as e:
            return {"ok": False, "error": f"psycopg2 not installed: {e}"}
        except (psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
>           return {"ok": False, "error": str(e)}
                                          ^^^^^^
E           Failed: Timeout (>30.0s) from pytest-timeout.

backend/app/postgres_repository.py:205: Failed
___________________ TestApiKeyManagement.test_create_api_key ___________________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7c5843c795b0>
client = <tests.conftest.LocalASGIClient object at 0x7c58409c9e20>

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
        assert signup.status_code == 201
        data_signup = signup.json()
        project_id = data_signup["project_id"]
        user_id = data_signup["user_id"]
        # Authenticate as the newly signed-up user
        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: [REDACTED]

        create = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Test Key", "scope": "read"},
            cookies=cookies,
        )
>       assert create.status_code == 201
E       assert 404 == 201
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_saas_api_keys.py:[REDACTED] AssertionError
___________________ TestApiKeyManagement.test_list_api_keys ____________________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7c5843c79070>
client = <tests.conftest.LocalASGIClient object at 0x7c5843120950>

    def test_list_api_keys(self, client: TestClient):
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-list@example.com",
                "password": "password123",
            },
        )
        data_signup = signup.json()
        project_id = data_signup["project_id"]
        user_id = data_signup["user_id"]

        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: [REDACTED]

        # Create a key
        client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "List Test", "scope": "write"},
            cookies=cookies,
        )

        list_resp = client.get(f"/api/saas/projects/{project_id}/keys", cookies=cookies)
>       assert list_resp.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_saas_api_keys.py:[REDACTED] AssertionError
___________________ TestApiKeyManagement.test_revoke_api_key ___________________

self = <tests.test_saas_api_keys.TestApiKeyManagement object at 0x7c5843c4ee10>
client = <tests.conftest.LocalASGIClient object at 0x7c5833233050>

    def test_revoke_api_key(self, client: TestClient):
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "test-revoke@example.com",
                "password": "password123",
            },
        )
        data_signup = signup.json()
        project_id = data_signup["project_id"]
        user_id = data_signup["user_id"]

        from app.auth.session import SESSION_COOKIE, create_session_cookie

        cookies = {SESSION_COOKIE: [REDACTED]

        create = client.post(
            f"/api/saas/projects/{project_id}/keys",
            json={"name": "Revoke Test", "scope": "read"},
            cookies=cookies,
        )
>       key_id = create.json()["id"]
                 ^^^^^^^^^^^^^^^^^^^
E       KeyError: 'id'

backend/tests/test_saas_api_keys.py:[REDACTED] KeyError
=============================== warnings summary ===============================
backend/tests/test_pagination_async.py::TestCanonicalFiveStrategyContract::test_strategy_enum_strings_match_across_layers
  backend/tests/test_pagination_async.py:509: PytestWarning: The test <Function test_strategy_enum_strings_match_across_layers> is marked with '@pytest.mark.asyncio' but it is not an async function. Please remove the asyncio mark. If the test is not marked explicitly, check for global marks applied via 'pytestmark'.
    def test_strategy_enum_strings_match_across_layers(self) -> None:

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/test_psycopg3_repository.py::TestFactorySelectsPsycopg3::test_default_driver_is_psycopg2
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]
FAILED backend/tests/test_saas_api_keys.py:[REDACTED]

```

## stderr

```text

```
