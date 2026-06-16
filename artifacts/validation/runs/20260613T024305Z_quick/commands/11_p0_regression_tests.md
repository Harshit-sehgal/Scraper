# p0_regression_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T02:43:07.792403+00:00
- end_time: 2026-06-13T02:43:08.534333+00:00
- duration_seconds: 0.74
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
backend/app/main.py:35: in <module>
    from app.routers.auth_profiles import router as auth_profiles_router
backend/app/routers/auth_profiles.py:20: in <module>
    from app.utils.encryption import decrypt as encryption_decrypt
E     File "/home/harshit/Documents/Work/Money/scraper/backend/app/utils/encryption.py", line 124
E       try:
E       ^^^
E   IndentationError: expected an indented block after 'if' statement on line 123

```
