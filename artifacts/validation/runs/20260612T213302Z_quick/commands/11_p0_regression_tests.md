# p0_regression_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T21:33:05.172855+00:00
- end_time: 2026-06-12T21:33:06.198193+00:00
- duration_seconds: 1.03
- exit_code: 4
- timeout_seconds: 180
- required: true
- redaction_applied: false

## stdout

```text

```

## stderr

```text
ImportError while loading conftest '/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py'.
backend/tests/conftest.py:251: in <module>
    import app.main
backend/app/main.py:52: in <module>
    from app.saas.router import router as saas_router
E     File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 726
E       raise HTTPException(status_code=404, detail="
E                                                   ^
E   SyntaxError: unterminated string literal (detected at line 726)

```
