# p0_regression_tests

- status: passed
- command: `/usr/bin/python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T14:38:41.123590+00:00
- end_time: 2026-06-17T14:38:51.962582+00:00
- duration_seconds: 10.84
- exit_code: 0
- timeout_seconds: 180
- required: true
- redaction_applied: false

## stdout

```text
.................................................................        [100%]
=============================== warnings summary ===============================
backend/app/routers/exports.py:61
  /home/harshit/Documents/Work/Money/scraper/backend/app/routers/exports.py:61: PydanticDeprecatedSince20: Pydantic V1 style `@validator` validators are deprecated. You should migrate to Pydantic V2 style `@field_validator` validators, see the migration guide for more details. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    @validator("format")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

```

## stderr

```text

```
