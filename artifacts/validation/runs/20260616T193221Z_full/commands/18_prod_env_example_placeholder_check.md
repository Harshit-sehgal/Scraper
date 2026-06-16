# prod_env_example_placeholder_check

- status: passed
- command: `/usr/bin/python3 scripts/check_prod_env.py --env-file /home/harshit/Documents/Work/Money/scraper/.env.production.example`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:37:20.500700+00:00
- end_time: 2026-06-16T19:37:20.530474+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 120
- required: true
- redaction_applied: true
- note: Expected fail for placeholder example env; this is not production readiness evidence.

## stdout

```text
DataForge Production Environment Check
  Env file: /home/harshit/Documents/Work/Money/scraper/.env.production.example
  Source priority: process environment overrides env-file values

  [FAIL]  DATAFORGE_API_KEY is too short (8 chars). Must be at least 16 characters.
  [FAIL]  DATAFORGE_API_KEY = [REDACTED] failed validation.
          Hint: Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
  [OK]    DATAFORGE_CORS_ORIGINS = ["https://yourdomain.com"]
  [FAIL]  DATAFORGE_DB_PASSWORD=[REDACTED] is a known default/placeholder value. Use a strong, unique password.
  [FAIL]  DATAFORGE_DB_PASSWORD = [REDACTED] failed validation.
          Hint: Must match POSTGRES_PASSWORD in docker-compose.prod.yml
  [FAIL]  DATAFORGE_STORAGE_BACKEND='sqlite'. Production requires 'postgres'.
  [FAIL]  DATAFORGE_STORAGE_BACKEND = 'sqlite' failed validation.
          Hint: Must be 'postgres' for production
  [FAIL]  DATAFORGE_DATABASE_URL password=[REDACTED] is a known default/placeholder value. Use a strong, unique password.
  [FAIL]  DATAFORGE_DATABASE_URL contains a weak or placeholder password.
  [FAIL]  DATAFORGE_DATABASE_URL = 'postgresql://dataforge:****@postgres:5432/dataforge' failed validation.
          Hint: Must be a postgresql:// URL matching docker-compose.prod.yml
  [OK]    DATAFORGE_WORKER_QUEUE = true
  [OK]    DATAFORGE_QUEUE_BACKEND = postgres
  [OK]    DATAFORGE_PG_DRIVER = psycopg3
  [FAIL]  DATAFORGE_METRICS_TOKEN=[REDACTED] is a known default/placeholder value. Generate a strong random key with: python3 -c "import secrets; print(secrets.token_hex(32))"
  [FAIL]  DATAFORGE_METRICS_TOKEN = [REDACTED] failed validation.
          Hint: Metrics scrape token for Prometheus. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
  [OK]    DATAFORGE_ENV = production
  [FAIL]  DATAFORGE_OPERATOR_API_KEY is too short (12 chars). Must be at least 16 characters.
  [FAIL]  DATAFORGE_OPERATOR_API_KEY = [REDACTED] failed validation.
          Hint: Operator key for job/selector mutations. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
  [FAIL]  DATAFORGE_ADMIN_API_KEY is too short (9 chars). Must be at least 16 characters.
  [FAIL]  DATAFORGE_ADMIN_API_KEY = [REDACTED] failed validation.
          Hint: Admin key for system-level operations. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
  [FAIL]  GRAFANA_PASSWORD=[REDACTED] is a known default/placeholder value. Set a strong, unique Grafana admin password.
  [FAIL]  GRAFANA_PASSWORD = [REDACTED] failed validation.
          Hint: Set a strong Grafana admin password (reject: admin, password, grafana, change-me)
  [OK]    API role keys are distinct

Result: ONE OR MORE CHECKS FAILED — fix the issues above before deploying.

```

## stderr

```text

```
