# Config And Environment Variable Audit

**Last refreshed:** 2026-06-08
**Status:** Centralized config exists; scattered env reads are limited and documented

## Config Source Of Truth

- `backend/app/config/__init__.py` (pydantic-settings with domain-specific mixins in `config/`)
- Uses `pydantic-settings` with `DATAFORGE_` prefix for most application settings.
- `DATAFORGE_DOTENV_PATH` now controls both `app.__init__` dotenv loading and the Pydantic settings env file, so `DATAFORGE_DOTENV_PATH=/dev/null` prevents local root `.env` bleed during validation.
- Runtime startup validation is in `backend/app/utils/prod_security_validator.py` and `scripts/check_prod_env.py`.

## Direct Env Reads Observed Outside `config/`

| File | Env usage | Classification |
| --- | --- | --- |
| `backend/app/__init__.py` | `DATAFORGE_DOTENV_PATH` | Acceptable dotenv loading boundary |
| `backend/app/utils/env.py` | generic environment helper | Acceptable utility |
| `scripts/check_prod_env.py` | env-file overlay and `DATAFORGE_SKIP_DB_CHECK` | Acceptable validation script |
| `scripts/run_worker.py` | `DATAFORGE_JOB_ID` | Acceptable worker script |
| `scripts/manual_test.py` | `DATAFORGE_API_BASE` | Manual script |
| `scripts/staging_smoke_test.py` | `STATE_FILE_PATH` test override | Smoke script |

## Dynamic Env Reads In `config/`

These are intentionally dynamic for testability/runtime overrides: `GROQ_API_KEY`, `DATAFORGE_WORKER_QUEUE`, `DATAFORGE_SMOKE_TEST_MODE`, `DATAFORGE_STORAGE_BACKEND`, `DATAFORGE_DATABASE_URL`, `DATAFORGE_QUEUE_BACKEND`, `DATAFORGE_STATE_FILE`, semantic state path aliases, and test selector persistence flags.

## Current Risks

- `GROQ_API_KEY` is intentionally not `DATAFORGE_` prefixed because external tooling commonly uses that name.
- Semantic state path aliases are partly backward-compatible and should be simplified later.
- Script-level env reads are acceptable but should be kept documented.
- Production values must be validated with `scripts/check_prod_env.py` before startup.
