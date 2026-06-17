# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T01:19:49.002872+00:00
- end_time: 2026-06-17T01:24:19.046702+00:00
- duration_seconds: 270.05
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
.....................................F.................................. [  3%]
........................................................................ [  5%]
........FF...................................ss......................... [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
..............................F......................................... [ 13%]
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
......................................FF................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
.FF.....................F............................................... [ 46%]
........................................................................ [ 47%]
.....................................................................sss [ 49%]
sssssssssssssssssss...........................ss........................ [ 51%]
.................................................ss..................... [ 53%]
.................F...................................................... [ 55%]
........................................................................ [ 57%]
................................................................ssssssss [ 59%]
sssss...................................s.....FFF....................... [ 61%]
.......FFF..............................FFF............................. [ 63%]
.FFF.................................F.................................. [ 65%]
........................................................................ [ 67%]
..........ss.............F.F............................................ [ 69%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
.......................................................sssssss.......... [ 82%]
........................................................................ [ 84%]
...F.FFFF........F.FF................................................... [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
......................................................s................. [ 95%]
..ss..sssssssssssssssssss............................................... [ 97%]
........................................................................ [ 99%]
...........                                                              [100%]
=================================== FAILURES ===================================
____________________________ test_healthcheck_route ____________________________

client = <tests.conftest.LocalASGIClient object at 0x74d2f6f2f050>

    def test_healthcheck_route(client) -> None:
        r = client.get("/health")
>       assert r.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_api_regressions.py:57: AssertionError
__________ TestPublicRouteDoesNotLog.test_public_route_no_auth_no_log __________

self = <tests.test_audit_logger_integration.TestPublicRouteDoesNotLog object at 0x74d2fdacda00>
client = <tests.conftest.LocalASGIClient object at 0x74d2fc2bdf70>
_setup_log_dir = PosixPath('/tmp/tmpn9i3kn5f')

    def test_public_route_no_auth_no_log(self, client, _setup_log_dir) -> None:
        """Public routes (outside /api/) should not trigger audit logging."""
        response = client.get("/health")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_audit_logger_integration.py:204: AssertionError
______ TestPublicRouteDoesNotLog.test_public_route_with_key_no_extra_log _______

self = <tests.test_audit_logger_integration.TestPublicRouteDoesNotLog object at 0x74d2fdab72c0>
client = <tests.conftest.LocalASGIClient object at 0x74d2f6f7b8f0>
_setup_log_dir = PosixPath('/tmp/tmp35pl1oih')

    def test_public_route_with_key_no_extra_log(self, client, _setup_log_dir) -> None:
        """Public routes should not log even if a valid key is provided."""
        response = client.get("/health", headers={"X-API-Key": "test_user_key"})
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_audit_logger_integration.py:212: AssertionError
_______ TestCSPReportOnlyHeader.test_health_response_carries_csp_header ________

self = <tests.test_csp_report_only.TestCSPReportOnlyHeader object at 0x74d2fd8ff5f0>
client = <tests.conftest.LocalASGIClient object at 0x74d2f67c1520>

    def test_health_response_carries_csp_header(self, client) -> None:
        r = client.get("/health")
>       assert r.status_code in (200, 401, 403, 503)
E       assert 404 in (200, 401, 403, 503)
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_csp_report_only.py:26: AssertionError
____________________ test_metrics_request_latency_tracking _____________________

client = <tests.conftest.LocalASGIClient object at 0x74d2f550cc20>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x74d2f7f70560>

    def test_metrics_request_latency_tracking(client, monkeypatch) -> None:
        """After making an API request, the latency histogram should capture it."""
        from app.metrics_collector import reset_for_testing
    
        reset_for_testing()
    
        # Make a request to an API endpoint to trigger latency tracking
        r = client.get("/health")
>       assert r.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_metrics.py:75: AssertionError
______________________ test_metrics_health_check_latency _______________________

client = <tests.conftest.LocalASGIClient object at 0x74d2f67c3ec0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x74d2f67c3830>

    def test_metrics_health_check_latency(client, monkeypatch) -> None:
        """Health check latency should be recorded when /ready is called."""
        from app.metrics_collector import reset_for_testing
    
        reset_for_testing()
    
        r = client.get("/ready")
>       assert r.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_metrics.py:93: AssertionError
________ TestOpenAPISpecContract.test_all_required_stable_paths_present ________

self = <tests.test_openapi_spec_contract.TestOpenAPISpecContract object at 0x74d2fce277d0>

    def test_all_required_stable_paths_present(self) -> None:
        spec = _generate()
        actual = set(spec["paths"].keys())
        missing = REQUIRED_STABLE_PATHS - actual
>       assert not missing, f"missing required stable paths: {sorted(missing)}"
E       AssertionError: missing required stable paths: ['/', '/health', '/ready']
E       assert not {'/', '/health', '/ready'}

backend/tests/test_openapi_spec_contract.py:96: AssertionError
_______________ TestOpenAPISpecContract.test_no_malformed_paths ________________

self = <tests.test_openapi_spec_contract.TestOpenAPISpecContract object at 0x74d2fce0bb90>

    def test_no_malformed_paths(self) -> None:
        spec = _generate()
        for path in spec["paths"]:
            assert path.startswith("/"), f"path must start with /: {path!r}"
>           assert not path.endswith("/") or path == "/", (
                f"path must not have a trailing slash (other than the root): {path!r}"
            )
E           AssertionError: path must not have a trailing slash (other than the root): '/api/'
E           assert (not True or '/api/' == '/'
E            +  where True = <built-in method endswith of str object at 0x74d2f793bd20>('/')
E            +    where <built-in method endswith of str object at 0x74d2f793bd20> = '/api/'.endswith
E             
E             - /
E             + /api/)

backend/tests/test_openapi_spec_contract.py:102: AssertionError
______________ TestOWASPTop10.test_a05_security_misconfiguration _______________

self = <tests.test_owasp.TestOWASPTop10 object at 0x74d2fce5cec0>
client = <tests.conftest.LocalASGIClient object at 0x74d2fc148bf0>

    def test_a05_security_misconfiguration(self, client: TestClient):
        """A05:2021 - Security Misconfiguration."""
        # Test that debug mode is not enabled in production
        response = client.get("/health")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_owasp.py:56: AssertionError
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
E         tests/test_openapi_spec_contract.py:18:1: 'pytest' imported but unused
E         
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/usr/bin/python3', '-m', 'pyflakes', 'app', 'tests'], returncode=1, stdout="tests/test_openapi_spec_contract.py:18:1: 'pytest' imported but unused\n", stderr='').returncode

backend/tests/test_pyflakes_fixes.py:20: AssertionError
__________________ test_route_auth_no_key[GET-/health-public] __________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f478bd70>
method = 'GET', path = '/health', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_no_key(client, method, path, min_role) -> None:
        """Without any API key, public routes work but /api/* returns 403."""
        expected = expected_status(method, path, "none", min_role)
        response = await client.request(method, path, headers=NO_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (no auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /health (no auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:226: AssertionError
__________________ test_route_auth_no_key[GET-/ready-public] ___________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f7c42120>
method = 'GET', path = '/ready', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_no_key(client, method, path, min_role) -> None:
        """Without any API key, public routes work but /api/* returns 403."""
        expected = expected_status(method, path, "none", min_role)
        response = await client.request(method, path, headers=NO_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (no auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /ready (no auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:226: AssertionError
_____________________ test_route_auth_no_key[GET-/-public] _____________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f68c9910>
method = 'GET', path = '/', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_no_key(client, method, path, min_role) -> None:
        """Without any API key, public routes work but /api/* returns 403."""
        expected = expected_status(method, path, "none", min_role)
        response = await client.request(method, path, headers=NO_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (no auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET / (no auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:226: AssertionError
_________________ test_route_auth_user_key[GET-/health-public] _________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f4522180>
method = 'GET', path = '/health', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_user_key(client, method, path, min_role) -> None:
        """With a USER-level API key, user routes work; operator/admin routes blocked."""
        expected = expected_status(method, path, "user", min_role)
        response = await client.request(method, path, headers=USER_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (user auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /health (user auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:237: AssertionError
_________________ test_route_auth_user_key[GET-/ready-public] __________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f7fdfe90>
method = 'GET', path = '/ready', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_user_key(client, method, path, min_role) -> None:
        """With a USER-level API key, user routes work; operator/admin routes blocked."""
        expected = expected_status(method, path, "user", min_role)
        response = await client.request(method, path, headers=USER_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (user auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /ready (user auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:237: AssertionError
____________________ test_route_auth_user_key[GET-/-public] ____________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f61d87d0>
method = 'GET', path = '/', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_user_key(client, method, path, min_role) -> None:
        """With a USER-level API key, user routes work; operator/admin routes blocked."""
        expected = expected_status(method, path, "user", min_role)
        response = await client.request(method, path, headers=USER_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (user auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET / (user auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:237: AssertionError
_______________ test_route_auth_operator_key[GET-/health-public] _______________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f54109e0>
method = 'GET', path = '/health', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_operator_key(client, method, path, min_role) -> None:
        """With an OPERATOR-level API key, user + operator routes work; admin routes blocked."""
        expected = expected_status(method, path, "operator", min_role)
        response = await client.request(method, path, headers=OPERATOR_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (operator auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /health (operator auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:248: AssertionError
_______________ test_route_auth_operator_key[GET-/ready-public] ________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f4ba37d0>
method = 'GET', path = '/ready', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_operator_key(client, method, path, min_role) -> None:
        """With an OPERATOR-level API key, user + operator routes work; admin routes blocked."""
        expected = expected_status(method, path, "operator", min_role)
        response = await client.request(method, path, headers=OPERATOR_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (operator auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /ready (operator auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:248: AssertionError
__________________ test_route_auth_operator_key[GET-/-public] __________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f7d64290>
method = 'GET', path = '/', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_operator_key(client, method, path, min_role) -> None:
        """With an OPERATOR-level API key, user + operator routes work; admin routes blocked."""
        expected = expected_status(method, path, "operator", min_role)
        response = await client.request(method, path, headers=OPERATOR_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (operator auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET / (operator auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:248: AssertionError
________________ test_route_auth_admin_key[GET-/health-public] _________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f543a630>
method = 'GET', path = '/health', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_admin_key(client, method, path, min_role) -> None:
        """With an ADMIN-level API key, all routes work."""
        expected = expected_status(method, path, "admin", min_role)
        response = await client.request(method, path, headers=ADMIN_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (admin auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /health (admin auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:259: AssertionError
_________________ test_route_auth_admin_key[GET-/ready-public] _________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f66bbad0>
method = 'GET', path = '/ready', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_admin_key(client, method, path, min_role) -> None:
        """With an ADMIN-level API key, all routes work."""
        expected = expected_status(method, path, "admin", min_role)
        response = await client.request(method, path, headers=ADMIN_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (admin auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET /ready (admin auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:259: AssertionError
___________________ test_route_auth_admin_key[GET-/-public] ____________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f4395640>
method = 'GET', path = '/', min_role = 'public'

    @pytest.mark.parametrize(("method", "path", "min_role"), ROUTE_MATRIX)
    @pytest.mark.asyncio
    async def test_route_auth_admin_key(client, method, path, min_role) -> None:
        """With an ADMIN-level API key, all routes work."""
        expected = expected_status(method, path, "admin", min_role)
        response = await client.request(method, path, headers=ADMIN_AUTH)
        if response.status_code == 422:
            return
>       assert response.status_code == expected, f"{method} {path} (admin auth): expected {expected}, got {response.status_code}"
E       AssertionError: GET / (admin auth): expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:259: AssertionError
_______________________ test_no_auth_public_routes_work ________________________

client = <tests.test_route_auth_matrix.LocalASGIClient object at 0x74d2f79f6510>

    @pytest.mark.asyncio
    async def test_no_auth_public_routes_work(client) -> None:
        """Public routes outside /api/ are accessible without any authentication."""
        response = await client.get("/health")
>       assert response.status_code == 200, f"Expected 200, got {response.status_code}"
E       AssertionError: Expected 200, got 404
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_route_auth_matrix.py:296: AssertionError
_______________ TestAuthentication.test_public_endpoint_no_auth ________________

self = <tests.test_security.TestAuthentication object at 0x74d2fc9a8d70>
client = <tests.conftest.LocalASGIClient object at 0x74d2f4801670>

    def test_public_endpoint_no_auth(self, client: TestClient):
        """Test public endpoints don't require auth."""
        response = client.get("/health")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_security.py:123: AssertionError
_____________________ TestSecurityHeaders.test_csp_in_html _____________________

self = <tests.test_security.TestSecurityHeaders object at 0x74d2fc9a97c0>
client = <tests.conftest.LocalASGIClient object at 0x74d2f62f3710>

    def test_csp_in_html(self, client: TestClient):
        """Test CSP is configured in HTML meta tags."""
        response = client.get("/")
        # CSP is set via meta tag in index.html, not HTTP header
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_security.py:146: AssertionError
__________________ TestHealthEndpoint.test_health_returns_200 __________________

self = <tests.test_storage_endpoints.TestHealthEndpoint object at 0x74d2fc517170>

    @pytest.mark.asyncio
    async def test_health_returns_200(self) -> None:
        """/health should always return 200 with status ok."""
        response = await client.get("/health")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_storage_endpoints.py:38: AssertionError
_______________ TestReadyEndpoint.test_ready_returns_storage_ok ________________

self = <tests.test_storage_endpoints.TestReadyEndpoint object at 0x74d2fc53d310>

    @pytest.mark.asyncio
    async def test_ready_returns_storage_ok(self) -> None:
        """/ready should check SQLite and return status."""
        response = await client.get("/ready")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_storage_endpoints.py:68: AssertionError
______________ TestReadyEndpoint.test_ready_includes_backend_type ______________

self = <tests.test_storage_endpoints.TestReadyEndpoint object at 0x74d2fc53d850>

    @pytest.mark.asyncio
    async def test_ready_includes_backend_type(self) -> None:
        """/ready should include the backend type."""
        response = await client.get("/ready")
        data = response.json()
>       assert "backend" in data
E       AssertionError: assert 'backend' in {'detail': 'Not Found'}

backend/tests/test_storage_endpoints.py:79: AssertionError
_____________ TestReadyEndpoint.test_ready_includes_schema_version _____________

self = <tests.test_storage_endpoints.TestReadyEndpoint object at 0x74d2fc53dd60>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x74d2f61132f0>

    @pytest.mark.asyncio
    async def test_ready_includes_schema_version(self, monkeypatch) -> None:
        """/ready should include schema_version >= 2."""
        self._mock_sqlite_backend(monkeypatch)
        response = await client.get("/ready")
        data = response.json()
>       assert "schema_version" in data
E       AssertionError: assert 'schema_version' in {'detail': 'Not Found'}

backend/tests/test_storage_endpoints.py:88: AssertionError
_________ TestReadyEndpoint.test_ready_includes_job_and_recycle_counts _________

self = <tests.test_storage_endpoints.TestReadyEndpoint object at 0x74d2fc53e2a0>

    @pytest.mark.asyncio
    async def test_ready_includes_job_and_recycle_counts(self) -> None:
        """/ready should include job_count and recycle_bin_count."""
        response = await client.get("/ready")
        data = response.json()
>       assert "job_count" in data
E       AssertionError: assert 'job_count' in {'detail': 'Not Found'}

backend/tests/test_storage_endpoints.py:96: AssertionError
_________ TestStorageStatusEndpoint.test_ready_reports_sqlite_backend __________

self = <tests.test_storage_endpoints.TestStorageStatusEndpoint object at 0x74d2fc53df10>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x74d2f7f714c0>

    @pytest.mark.asyncio
    async def test_ready_reports_sqlite_backend(self, monkeypatch) -> None:
        """/ready should report sqlite backend when using SQLite."""
        self._mock_sqlite_backend(monkeypatch)
        response = await client.get("/ready")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_storage_endpoints.py:219: AssertionError
_______ TestReadyWithMockedPostgres.test_ready_reports_postgres_backend ________

self = <tests.test_storage_endpoints.TestReadyWithMockedPostgres object at 0x74d2fc550290>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x74d2f7f73dd0>

    @pytest.mark.asyncio
    async def test_ready_reports_postgres_backend(self, monkeypatch) -> None:
        """/ready should report postgres backend when Postgres repository is active."""
        mock_repo = self._make_mock_postgres_repo(healthy=True)
        monkeypatch.setattr("app.main.get_job_repository", lambda: mock_repo)
    
        response = await client.get("/ready")
>       assert response.status_code == 200
E       assert 404 == 200
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_storage_endpoints.py:271: AssertionError
__ TestReadyWithMockedPostgres.test_ready_returns_503_when_postgres_unhealthy __

self = <tests.test_storage_endpoints.TestReadyWithMockedPostgres object at 0x74d2fc5507a0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x74d2f7f73d10>

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_postgres_unhealthy(self, monkeypatch) -> None:
        """/ready should return 503 when Postgres repository is unhealthy."""
        mock_repo = self._make_mock_postgres_repo(healthy=False)
        monkeypatch.setattr("app.main.get_job_repository", lambda: mock_repo)
    
        response = await client.get("/ready")
>       assert response.status_code == 503
E       assert 404 == 503
E        +  where 404 = <Response [404 Not Found]>.status_code

backend/tests/test_storage_endpoints.py:285: AssertionError
=============================== warnings summary ===============================
backend/tests/test_pagination_async.py::TestCanonicalFiveStrategyContract::test_strategy_enum_strings_match_across_layers
  backend/tests/test_pagination_async.py:510: PytestWarning: The test <Function test_strategy_enum_strings_match_across_layers> is marked with '@pytest.mark.asyncio' but it is not an async function. Please remove the asyncio mark. If the test is not marked explicitly, check for global marks applied via 'pytestmark'.
    def test_strategy_enum_strings_match_across_layers(self) -> None:

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/test_api_regressions.py::test_healthcheck_route - assert...
FAILED backend/tests/test_audit_logger_integration.py::TestPublicRouteDoesNotLog::test_public_route_no_auth_no_log
FAILED backend/tests/test_audit_logger_integration.py::TestPublicRouteDoesNotLog::test_public_route_with_key_no_extra_log
FAILED backend/tests/test_csp_report_only.py::TestCSPReportOnlyHeader::test_health_response_carries_csp_header
FAILED backend/tests/test_metrics.py::test_metrics_request_latency_tracking
FAILED backend/tests/test_metrics.py::test_metrics_health_check_latency - ass...
FAILED backend/tests/test_openapi_spec_contract.py::TestOpenAPISpecContract::test_all_required_stable_paths_present
FAILED backend/tests/test_openapi_spec_contract.py::TestOpenAPISpecContract::test_no_malformed_paths
FAILED backend/tests/test_owasp.py::TestOWASPTop10::test_a05_security_misconfiguration
FAILED backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean - AssertionE...
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_no_key[GET-/health-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_no_key[GET-/ready-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_no_key[GET-/-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_user_key[GET-/health-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_user_key[GET-/ready-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_user_key[GET-/-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_operator_key[GET-/health-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_operator_key[GET-/ready-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_operator_key[GET-/-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_admin_key[GET-/health-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_admin_key[GET-/ready-public]
FAILED backend/tests/test_route_auth_matrix.py::test_route_auth_admin_key[GET-/-public]
FAILED backend/tests/test_route_auth_matrix.py::test_no_auth_public_routes_work
FAILED backend/tests/test_security.py::TestAuthentication::test_public_endpoint_no_auth
FAILED backend/tests/test_security.py::TestSecurityHeaders::test_csp_in_html
FAILED backend/tests/test_storage_endpoints.py::TestHealthEndpoint::test_health_returns_200
FAILED backend/tests/test_storage_endpoints.py::TestReadyEndpoint::test_ready_returns_storage_ok
FAILED backend/tests/test_storage_endpoints.py::TestReadyEndpoint::test_ready_includes_backend_type
FAILED backend/tests/test_storage_endpoints.py::TestReadyEndpoint::test_ready_includes_schema_version
FAILED backend/tests/test_storage_endpoints.py::TestReadyEndpoint::test_ready_includes_job_and_recycle_counts
FAILED backend/tests/test_storage_endpoints.py::TestStorageStatusEndpoint::test_ready_reports_sqlite_backend
FAILED backend/tests/test_storage_endpoints.py::TestReadyWithMockedPostgres::test_ready_reports_postgres_backend
FAILED backend/tests/test_storage_endpoints.py::TestReadyWithMockedPostgres::test_ready_returns_503_when_postgres_unhealthy

```

## stderr

```text

```
