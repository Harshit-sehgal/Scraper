# p0_regression_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T02:43:52.887690+00:00
- end_time: 2026-06-13T02:44:06.093796+00:00
- duration_seconds: 13.21
- exit_code: 1
- timeout_seconds: 180
- required: true
- redaction_applied: false

## stdout

```text
................................................................F        [100%]
=================================== FAILURES ===================================
______________ test_route_auth_matrix_has_no_user_level_mutations ______________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x754d8b183500>
tmp_path = PosixPath('/tmp/pytest-of-harshit/pytest-501/test_route_auth_matrix_has_no_0')

    def test_route_auth_matrix_has_no_user_level_mutations(monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("DATAFORGE_DOTENV_PATH", "/dev/null")
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "jobs_state.json"))
        monkeypatch.setenv("DATAFORGE_SEMANTIC_STATE_PATH", str(tmp_path / "semantic_state.json"))

        matrix = _load_module().build_matrix()

        # Endpoints that are intentionally unauthenticated mutation routes. Each
        # entry is a (method, path) pair that has a documented reason for being
        # open (e.g. browser-generated reports). The reason is enforced by the
        # body-size middleware (5 MB cap) and the global /api/* rate limiter.
        UNAUTHENTICATED_MUTATIONS = {
            ("POST", "/api/system/csp-violations"),  # browser CSP report, no key
            ("POST", "/api/session"),  # self-service auth — any authenticated user can create a session
            ("DELETE", "/api/session"),  # self-service auth — any authenticated user can clear their session
            ("POST", "/api/saas/signup"),  # self-service account creation
            ("POST", "/api/saas/aup/accept"),  # P1-COMPLIANCE-001: AUP acceptance (idempotent, any authenticated user)
        }

        unsafe = [
            row
            for row in matrix
            if (
                row.path.startswith("/api/")
                and row.method != "GET"
                and row.access == "authenticated-user"
                and (row.method, row.path) not in UNAUTHENTICATED_MUTATIONS
            )
        ]

>       assert unsafe == []
E       AssertionError: assert [RouteAuthRow...)', notes='')] == []
E
E         Left contains one more item: RouteAuthRow(method='DELETE', path='/api/user/data', access='authenticated-user', enforcement='require_role([admin, operator, user])', notes='')
E         Use -v to get more diff

backend/tests/test_route_auth_matrix_generator.py:111: AssertionError
=========================== short test summary info ============================
FAILED backend/tests/test_route_auth_matrix_generator.py::test_route_auth_matrix_has_no_user_level_mutations

```

## stderr

```text

```
