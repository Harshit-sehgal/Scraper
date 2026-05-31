# Config & Environment Variable Audit

> **Current as of:** 2026-05-31
> **Audit of:** `backend/app/config.py` and scattered env reads

## Verdict: **Config is well-centralized. No major issues found.**

## Config Source of Truth

- **File:** `backend/app/config.py` (684 lines)
- **Pattern:** `pydantic-settings` with `env_prefix = "DATAFORGE_"`
- **Instance:** `from app.config import settings` — provides typed, documented settings

## Direct os.getenv / os.environ Calls Outside config.py

Only **4 non-config files** have direct env reads, all acceptable:

| File | Line | Env Var | Classification |
|---|---|---|---|
| `backend/app/__init__.py` | 8 | `DATAFORGE_DOTENV_PATH` | **Acceptable** — dotenv path override, called once at import |
| `backend/app/utils/env.py` | 6 | (arbitrary) | **Acceptable** — generic utility `env_int()` function |
| `scripts/run_worker.py` | 108 | `DATAFORGE_JOB_ID` | **Acceptable** — standalone script |
| `scripts/manual_test.py` | 34 | `DATAFORGE_API_BASE` | **Acceptable** — standalone script |
| `scripts/check_prod_env.py` | 400 | `DATAFORGE_SKIP_DB_CHECK` | **Acceptable** — standalone script |

## Dynamic Properties in config.py

These properties read env vars at call time (not import time) for testability and runtime flexibility:

| Property | Env Var | Purpose | Acceptable? |
|---|---|---|---|
| `GROQ_API_KEY` | `GROQ_API_KEY` | LLM API key (no DATAFORGE_ prefix — external) | ✅ SDK convention |
| `WORKER_QUEUE` | `DATAFORGE_WORKER_QUEUE` | Toggle worker queue mode | ✅ |
| `SMOKE_TEST_MODE` | `DATAFORGE_SMOKE_TEST_MODE` | Toggle smoke test mode | ✅ |
| `STORAGE_BACKEND` | `DATAFORGE_STORAGE_BACKEND` | Select SQLite or Postgres | ✅ |
| `DATABASE_URL` | `DATAFORGE_DATABASE_URL` | Postgres connection string | ✅ |
| `QUEUE_BACKEND_DYNAMIC` | `DATAFORGE_QUEUE_BACKEND` | Select queue backend | ✅ |
| `STATE_FILE` | `DATAFORGE_STATE_FILE` | Override state file path | ✅ |
| `SEMANTIC_STATE_PATH_DYNAMIC` | `SEMANTIC_STATE_PATH` | Override semantic state path | ✅ |
| `TEST_SELECTOR_DECAY_PERSISTENCE` | `TEST_SELECTOR_DECAY_PERSISTENCE` | Toggle persistence in tests | ✅ |

## Required Environment Variables

| Env Var | Required? | Default | Purpose |
|---|---|---|---|
| `DATAFORGE_ENV` | No | `development` | App environment (`development` / `production`) |
| `DATAFORGE_API_KEY` | No (recommended for prod) | `""` | API key for user-level access |
| `DATAFORGE_ADMIN_API_KEY` | No (encouraged for prod) | `""` | Admin API key for privileged routes |
| `DATAFORGE_OPERATOR_API_KEY` | No | `""` | Operator API key for job routes |
| `DATAFORGE_METRICS_TOKEN` | No | `""` | Bearer token for /metrics endpoint |
| `DATAFORGE_STORAGE_BACKEND` | No | `sqlite` | Storage backend (`sqlite` / `postgres`) |
| `DATAFORGE_DATABASE_URL` | Yes if postgres | `""` | Postgres connection string |
| `GROQ_API_KEY` | No (most features work without LLM) | `""` | Groq API key for LLM features |

## Findings

### ✅ Positive
1. **Centralized config** — All tunables in one file with docstrings
2. **Typed settings** — `pydantic-settings` with type checking
3. **Dynamic properties** — Runtime env reads for testability
4. **Backwards-compatible aliases** — `__getattr__` provides old name → new name mapping
5. **Production safety** — `CORS_ORIGINS` validated in production startup
6. **No secret leaks** — All `.env.example` files have safe placeholders

### ⚠️ Minor Issues
1. **GROQ_API_KEY uses different prefix** — Uses `GROQ_API_KEY` (no `DATAFORGE_` prefix) because the Groq SDK reads the same var. This is standard practice for API keys.
2. **SEMANTIC_STATE_PATH_DYNAMIC uses non-prefixed var** — Uses `SEMANTIC_STATE_PATH` instead of `DATAFORGE_SEMANTIC_STATE_PATH`. Minor inconsistency but documented.
3. **Scripts use direct env reads** — Acceptable for standalone scripts, but could be migrated to use config.py

### ❌ No Critical Issues Found
- No real secrets in source control
- No `.env` files committed (only `.example` files)
- No production credentials in tests
- All env reads are accounted for
