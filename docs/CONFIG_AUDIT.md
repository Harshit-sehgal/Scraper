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
| `backend/app/distributed.py` | `DATAFORGE_NODE_ROLE` | Acceptable direct env read (role: api/worker/scheduler/standalone) |

## Dynamic Env Reads In `config/`

These are intentionally dynamic for testability/runtime overrides: `GROQ_API_KEY`, `DATAFORGE_WORKER_QUEUE`, `DATAFORGE_SMOKE_TEST_MODE`, `DATAFORGE_STORAGE_BACKEND`, `DATAFORGE_DATABASE_URL`, `DATAFORGE_QUEUE_BACKEND`, `DATAFORGE_STATE_FILE`, semantic state path aliases, and test selector persistence flags.

## `.env.example` Placeholders Not Yet Code-Consumed

These vars are defined in `.env.example` with default values but are not yet read by any
`.py` file. They serve as configuration placeholders for future features. They are listed
here for reference:

| Environment Variable | Category |
| --- | --- |
| `DATAFORGE_ANTIBOT_BLOCK_HISTORY_SIZE` | Anti-bot |
| `DATAFORGE_ANTIBOT_UA_HISTORY_SIZE` | Anti-bot |
| `DATAFORGE_BROWSER_MAX_PROCESSES` | Browser |
| `DATAFORGE_BROWSER_MAX_REUSABLE_CONTEXTS` | Browser |
| `DATAFORGE_CAPTCHA_API_KEY` | Captcha |
| `DATAFORGE_CAPTCHA_PROVIDER` | Captcha |
| `DATAFORGE_CAPTCHA_SOLVER_ENABLED` | Captcha |
| `DATAFORGE_CAPTCHA_SOLVE_TIMEOUT_S` | Captcha |
| `DATAFORGE_CF_HARVESTER_MAX_RENDER_WAIT_S` | Cloudflare |
| `DATAFORGE_CF_HARVESTER_TIMEOUT_S` | Cloudflare |
| `DATAFORGE_EMPTY_RESPONSE_DATA_SIGNAL_THRESHOLD` | Detection |
| `DATAFORGE_EMPTY_RESPONSE_LOW_SIGNAL_COUNT` | Detection |
| `DATAFORGE_EMPTY_RESPONSE_MODERATE_SIGNAL_COUNT` | Detection |
| `DATAFORGE_GEOCODER_USER_AGENT` | Geocoder |
| `DATAFORGE_HTTPX_BASIC_USER_AGENT` | HTTP |
| `DATAFORGE_JOB_MAX_CONCURRENT_PER_USER` | Jobs |
| `DATAFORGE_LLM_CIRCUIT_FAILURE_THRESHOLD` | LLM Circuit Breaker |
| `DATAFORGE_LLM_CIRCUIT_HALF_OPEN_MAX_PROBES` | LLM Circuit Breaker |
| `DATAFORGE_LLM_CIRCUIT_OPEN_WINDOW_SECONDS` | LLM Circuit Breaker |
| `DATAFORGE_NOTIFICATION_TIMEOUT_SECONDS` | Notifications |
| `DATAFORGE_PROXY_PROVIDER_FILE` | Proxy |
| `DATAFORGE_PROXY_PROVIDER_REFRESH_INTERVAL_S` | Proxy |
| `DATAFORGE_PROXY_PROVIDER_TYPE` | Proxy |
| `DATAFORGE_PROXY_PROVIDER_URL` | Proxy |
| `DATAFORGE_PROXY_URLS` | Proxy |
| `DATAFORGE_QUALITY_COMPLETENESS_WEIGHT` | Quality |
| `DATAFORGE_QUALITY_DETAIL_RECORD_LIMIT` | Quality |
| `DATAFORGE_QUALITY_TREND_ALERT_THRESHOLD` | Quality |
| `DATAFORGE_QUALITY_TREND_DOMAIN_KEY_DELIMITER` | Quality |
| `DATAFORGE_QUALITY_TREND_MAX_SAMPLES` | Quality |
| `DATAFORGE_QUALITY_TREND_PAGE_LIMIT` | Quality |
| `DATAFORGE_QUALITY_TREND_WINDOW_DAYS` | Quality |
| `DATAFORGE_QUALITY_TYPE_CONFORMANCE_WEIGHT` | Quality |
| `DATAFORGE_SESSION_NO_EPHEMERAL_MAX_CONFIDENCE` | Session |
| `DATAFORGE_SMTP_FROM` | SMTP |
| `DATAFORGE_SMTP_HOST` | SMTP |
| `DATAFORGE_SMTP_PASS` | SMTP |
| `DATAFORGE_SMTP_PORT` | SMTP |
| `DATAFORGE_SMTP_USER` | SMTP |
| `DATAFORGE_SMTP_USE_SSL` | SMTP |
| `DATAFORGE_ZERO_RESULT_AUTH_PATTERNS` | Zero-result |

## Current Risks

- `GROQ_API_KEY` is intentionally not `DATAFORGE_` prefixed because external tooling commonly uses that name.
- Semantic state path aliases are partly backward-compatible and should be simplified later.
- Script-level env reads are acceptable but should be kept documented.
- Production values must be validated with `scripts/check_prod_env.py` before startup.
