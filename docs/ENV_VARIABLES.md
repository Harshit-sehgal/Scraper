# Environment Variables Reference

## Overview

DataForge uses `DATAFORGE_` prefixed environment variables for configuration. All variables are defined in `backend/app/config/` using pydantic-settings.

## Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `DATAFORGE_ENABLE_RELOAD` | `false` | Enable uvicorn `--reload` / debug logging in the dev container target; leave unset for production/default compose runs |
| `DATAFORGE_DOTENV_PATH` | `.env` | Path to dotenv file |
| `DATAFORGE_STORAGE_BACKEND` | `sqlite` | Storage backend: `sqlite` or `postgres` |
| `DATAFORGE_DATABASE_URL` | - | PostgreSQL connection URL (required for postgres backend) |
| `DATAFORGE_STATE_FILE` | *unset* | Legacy alias for `DATAFORGE_STATE_FILE_PATH`. Read by `STATE_FILE_PATH_DYNAMIC` when the path override is not configured. |
| `DATAFORGE_STATE_FILE_PATH` | `""` | Override path for `jobs_state.json` (empty = `./backend/data/jobs_state.json`) |
| `DATAFORGE_SEMANTIC_STATE_PATH` | `data/semantic_state.json` | Path to semantic state file |

## Production Ingress

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_NGINX_SSL_DIR` | `./.secrets/nginx` | Directory mounted into production nginx at `/etc/nginx/ssl`; must contain `fullchain.pem` and `privkey.pem` for real TLS deployments |
| `DATAFORGE_CERTBOT_WEBROOT` | `./.secrets/certbot/www` | Directory mounted into production nginx at `/var/www/certbot` for ACME http-01 challenge files |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_API_KEY` | - | User-level API key (read access) |
| `DATAFORGE_OPERATOR_API_KEY` | - | Operator API key (write access; env-backed operators have all-access with no org/project scope) |
| `DATAFORGE_ADMIN_API_KEY` | - | Admin API key (global all-access) |
| `DATAFORGE_SESSION_SECRET` | - | Session signing secret (auto-generated if not set) |
| `DATAFORGE_ALLOW_INSECURE_DEV_AUTH` | `false` | Allow insecure auth in development |
| `DATAFORGE_ENABLE_OPERATOR_CROSS_TENANT` | `false` | Allow env-backed operator keys (without org/project scope) cross-tenant all-access. Must be explicitly enabled for self-hosted internal operator scripts; keep disabled for SaaS deployments.
| `DATAFORGE_BILLING_WEBHOOK_SECRET` | - | Shared secret for billing webhook HMAC/shared-secret verification |

## Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_RATE_LIMIT_GLOBAL` | `600` | Global rate limit (requests/minute) |
| `DATAFORGE_RATE_LIMIT_PER_IP` | `100` | Per-IP rate limit (requests/minute) |
| `DATAFORGE_RATE_LIMIT_PER_IP_ENABLED` | `true` | Enable per-IP rate limiting |
| `DATAFORGE_RATE_LIMIT_DB_BACKED` | `false` | Use database-backed rate limits |
| `DATAFORGE_RATE_LIMITER_MAX_COUNTERS` | `5000` | Maximum in-memory rate limiter counter entries before pruning oldest entries

## Worker Queue

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_WORKER_QUEUE` | `memory` | Queue backend: `memory`, `postgres` |
| `DATAFORGE_WORKER_HEARTBEAT_ID` | - | Worker heartbeat identifier |
| `DATAFORGE_WORKER_HEARTBEAT_TTL` | `60` | Worker heartbeat freshness window in seconds for the worker healthcheck |

## Notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TELEGRAM_ENABLED` | `false` | Enable Telegram notifications |
| `DATAFORGE_TELEGRAM_BOT_TOKEN` | - | Telegram bot token |
| `DATAFORGE_TELEGRAM_CHAT_ID` | - | Telegram chat ID |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_METRICS_TOKEN` | - | Token for metrics endpoint |
| `DATAFORGE_TRUSTED_PROXIES` | - | Comma-separated list of trusted proxies |
| `DATAFORGE_CORS_ORIGINS` | - | Comma-separated list of allowed CORS origins |
| `DATAFORGE_ALLOWED_INTERNAL_HOSTS` | - | Comma-separated list of allowed internal hosts |
| `DATAFORGE_DENYLIST_DB_PATH` | - | Optional SQLite path for the operator-managed domain denylist |
| `DATAFORGE_ENCRYPTION_KEY` | - | Base64 AES-GCM key for auth-profile storage state encryption |
| `DATAFORGE_ENCRYPTION_UID_FP_SALT` | - | Salt used in encryption UID fingerprint derivation for user identity hashing
| `DATAFORGE_ENCRYPTION_SALT` | `default-salt-change-in-prod` | Salt used in encryption key derivation for auth-profile encryption |
| `DATAFORGE_REDIS_URL` | - | Redis connection URL for rate-limiter distributed storage |
| `DATAFORGE_ENCRYPTION_KEY_` | - | Prefix for versioned encryption keys such as `DATAFORGE_ENCRYPTION_KEY_V1` |
| `DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION` | `v1` | Active version used for new encrypted payloads |
| `DATAFORGE_AUTH_PROFILES_FILE` | `data/auth_profiles.json` | Path to the file-backed auth-profile store (used by `AuthProfileStore` in `app/utils/auth_profile_store.py`) |
| `DATAFORGE_BILLING_SUBSCRIPTIONS_FILE` | `data/billing_subscriptions.json` | Path to the file-backed billing-subscription store |
| `DATAFORGE_WORKFLOW_RUNS_FILE` | `data/workflow_runs.json` | Path to the file-backed workflow-run history store |
| `DATAFORGE_DISCOVERY_DIRECTORY_DOMAINS` | - | Comma-separated allowlist of domains for auto-discovery directory mode |
| `DATAFORGE_LOCATION_WORDS` | - | Comma-separated extra location words to recognise when extracting location fields |
| `DATAFORGE_LOCATION_WORDS_FILE` | - | Path to a file containing extra location words (one per line) |
| `DATAFORGE_DB_PASSWORD` | - | Postgres password (fallback used by backup/restore scripts when `DATAFORGE_DATABASE_URL` is unset) |

## Operations Scripts

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_BACKUP_KEEP_DAYS` | `30` | Retention window for `scripts/backup_postgres.sh`; set to `0` to skip the post-backup retention sweep |
| `DATAFORGE_RESTORE_SKIP_VERIFY` | `0` | Set to `1` to bypass `scripts/restore_postgres.sh` post-restore row-count verification during an emergency restore |
| `DATAFORGE_DRILL_ALLOW_REMOTE` | `0` | Set to `1` to allow `scripts/run_alert_delivery_drill.py` to target a non-localhost Alertmanager URL without `--allow-remote-host` |

## Experimental Features

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES` | `false` | Enable experimental API routes |
| `DATAFORGE_SMOKE_TEST_MODE` | `false` | Enable smoke test mode |

## LLM Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | - | Groq API key for LLM operations |
| `DATAFORGE_GROQ_API_KEY` | - | Alternative prefix for Groq API key (takes precedence over `GROQ_API_KEY`) |

## Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TEST_DETERMINISTIC_ENV_VAR` | - | Test-only environment variable |
| `DATAFORGE_TEST_SELECTOR_DECAY_PERSISTENCE` | `false` | Persist selector decay snapshots during tests |

## Direct Environment Reads

These are acceptable direct environment reads outside the config module:

| File | Variable | Purpose |
|------|----------|---------|
| `backend/app/__init__.py` | `DATAFORGE_DOTENV_PATH` | Dotenv loading boundary |
| `backend/app/utils/env.py` | Generic helper | Environment utility |
| `backend/app/billing/checkout.py` | `DATAFORGE_PUBLIC_BASE_URL` | Public base URL for constructing checkout approval URLs |
| `backend/app/postgres_repository.py` | `DATAFORGE_DB_CONNECT_TIMEOUT` | Postgres connect timeout (default `10`); test suite uses `1` for fast-fail |
| `backend/app/rate_limiter.py` | `DATAFORGE_REDIS_URL` | Redis connection URL for distributed rate-limiter storage |
| `backend/app/utils/encryption.py` | `DATAFORGE_ENCRYPTION_SALT` | Encryption salt for auth-profile key derivation |
| `backend/app/utils/data_retention.py` | `DATAFORGE_RETENTION_DAYS_COMPLETED` | Days to retain completed jobs (default `30`) |
| `backend/app/utils/data_retention.py` | `DATAFORGE_RETENTION_DAYS_RECYCLE` | Days to retain recycle-bin jobs (default `30`) |
| `backend/app/utils/data_retention.py` | `DATAFORGE_RETENTION_DAYS_IDEMPOTENCY` | Days to retain idempotency keys (default `7`) |
| `backend/app/lifespan.py` | `DATAFORGE_RETENTION_INTERVAL` | Retention sweep interval in seconds (default `43200` = 12h) |
| `backend/app/admin_denylist.py` | `DATAFORGE_JOB_STORE_PATH` | Override SQLite job-store database path |
| `scripts/check_prod_env.py` | `DATAFORGE_SKIP_DB_CHECK` | Validation script |
| `scripts/backup_postgres.sh` | `DATAFORGE_BACKUP_KEEP_DAYS` | Postgres backup retention |
| `scripts/restore_postgres.sh` | `DATAFORGE_RESTORE_SKIP_VERIFY` | Emergency restore verification bypass |
| `scripts/run_alert_delivery_drill.py` | `DATAFORGE_DRILL_ALLOW_REMOTE` | Explicit remote-host drill opt-in |
| `scripts/run_worker.py` | `DATAFORGE_JOB_ID` | Worker script |
| `scripts/manual_test.py` | `DATAFORGE_API_BASE` | Manual testing |

## Browser / Playwright

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_PLAYWRIGHT_TIMEOUT` | `45000` | Max ms to wait for `networkidle` (primary navigation gate) |
| `DATAFORGE_PLAYWRIGHT_FALLBACK_TIMEOUT` | `35000` | Max ms for the `domcontentloaded` fallback when `networkidle` fails |
| `DATAFORGE_PLAYWRIGHT_HEADLESS` | `true` | Run Chromium headless; set `false` for local debugging |
| `DATAFORGE_BROWSER_VIEWPORT_WIDTH` | `1280` | Default browser viewport width |
| `DATAFORGE_BROWSER_VIEWPORT_HEIGHT` | `900` | Default browser viewport height |
| `DATAFORGE_BROWSER_MAX_CONTEXTS` | `10` | Cap on concurrent isolated browser contexts (semaphore) |
| `DATAFORGE_BROWSER_CONTEXT_LIFETIME` | `50` | Max page fetches a reusable context serves before rotation |
| `DATAFORGE_BROWSER_IDLE_TIMEOUT` | `300` | Seconds the browser may sit idle before close |
| `DATAFORGE_BROWSER_MAX_CUMULATIVE_FETCHES` | `200` | Cumulative fetch count at which the pool triggers a hard recycle |
| `DATAFORGE_BROWSER_MAX_RSS_MEMORY_MB` | `1024` | RSS memory (MB) ceiling that triggers a hard recycle |
| `DATAFORGE_BROWSER_DRAIN_POLL_INTERVAL` | `0.5` | Seconds between drain checks when waiting for in-flight fetches |
| `DATAFORGE_BROWSER_CLEANUP_INTERVAL` | `60` | Seconds between background BrowserPool cleanup sweeps |
| `DATAFORGE_BROWSER_SECURITY_HARDENING` | `true` | Pass `--disable-features=AutomationControlled` and other Chromium hardening flags |
| `DATAFORGE_PAGE_SETTLE_DELAY` | `2.0` | Seconds to wait after `networkidle` for late JS rendering |
| `DATAFORGE_PAGE_FALLBACK_EXTRA_WAIT` | `5.0` | Extra seconds to pause after `domcontentloaded` fallback |
| `DATAFORGE_PAGE_SCROLL_DELAY` | `0.5` | Seconds to wait after each auto-scroll pass |
| `DATAFORGE_POST_SCROLL_RESET_DELAY` | `0.2` | Seconds to wait after resetting scroll position to top |
| `DATAFORGE_DOM_STABILIZATION_INTERVAL` | `200` | Milliseconds between DOM mutation checks |
| `DATAFORGE_PLAYWRIGHT_STEALTH` | `true` | Enable fingerprint-randomization overrides on every page |
| `DATAFORGE_CF_HARVESTER_ENABLED` | `false` | Enable Cloudflare cf_clearance cookie harvester for challenge page auto-resolution
| `DATAFORGE_STEALTH_UA_POOL` | *(long UA list)* | Comma-separated pool of user-agent strings for UA rotation |
| `DATAFORGE_STEALTH_VIEWPORT_WIDTHS` | `1280,1366,...` | Comma-separated viewport widths pool for stealth variant |
| `DATAFORGE_STEALTH_VIEWPORT_HEIGHTS` | `720,768,...` | Comma-separated viewport heights pool |
| `DATAFORGE_STEALTH_DEVICE_SCALE_FACTORS` | `1.0,1.25,1.5,2.0` | Comma-separated device scale factor pool |
| `DATAFORGE_STEALTH_NAVIGATOR_LANGUAGES` | `en-US,en` | Comma-separated languages for `navigator.languages` |
| `DATAFORGE_STEALTH_TIMEZONE_POOL` | *(long tz list)* | Comma-separated IANA timezones for stealth variant |
| `DATAFORGE_STEALTH_HARDWARE_CONCURRENCY` | `4` | Value reported for `navigator.hardwareConcurrency` |
| `DATAFORGE_STEALTH_ACCEPT_LANGUAGE` | `en-US,en;q=0.9` | Accept-Language header sent on every HTTP fetch |
| `DATAFORGE_STEALTH_DEFAULT_LOCALE` | `en-US` | Default `navigator.language` for browser contexts |
| `DATAFORGE_PROFILE_MAX_WAIT` | `30` | Max seconds for a selector profile to find its `wait_for` selector |
| `DATAFORGE_PROFILE_CONTAINER_POLL_ATTEMPTS` | `8` | Max polls while waiting for a stable item-container count |
| `DATAFORGE_PROFILE_CONTAINER_STABLE_POLLS` | `2` | Consecutive stable container counts required before extraction |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_EXACT` | `1000.0` | Score when a field name matches exactly |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_PLURAL` | `85.0` | Score when field name matches plural form |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_TOKEN_OVERLAP` | `55.0` | Score based on word overlap between field name and profile |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_SUBSTRING` | `45.0` | Score when one name is a substring of the other |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_REVERSE_SUBSTRING` | `40.0` | Reverse-substring variant score |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_SYNONYM` | `50.0` | Score when synonyms match (token-aware) |
| `DATAFORGE_PROFILE_ALIGNMENT_SCORE_TYPE_BONUS` | `25.0` | Type-match bonus added on top of name alignment |
| `DATAFORGE_PROFILE_ALIGNMENT_NEGATIVE_PENALTY` | `500.0` | Penalty for negative field alignment |
| `DATAFORGE_PROFILE_SELECTOR_TYPE_COMPATIBILITY` | *(dict)* | Selector-type compatibility mapping for profile alignment |

## Extract & Scoring

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_MAX_RECORDS_PER_SOURCE` | `25` | Max records kept from a single URL after scoring/dedup |
| `DATAFORGE_DEFAULT_MIN_RECORD_SCORE` | `0.35` | Minimum quality score for record acceptance |
| `DATAFORGE_RECORD_ACCEPTANCE_FACTOR` | `0.8` | Factor applied to min_record_score for final gate |
| `DATAFORGE_SCORE_GATE_THRESHOLD_FACTOR` | `0.5` | Factor of min_record_score for quality gate floor |
| `DATAFORGE_SCORE_GATE_ABSOLUTE_MIN` | `0.1` | Absolute floor for quality gate threshold |
| `DATAFORGE_SCORE_QUALITY_WEIGHT` | `0.55` | Scoring weight for record quality |
| `DATAFORGE_SCORE_COVERAGE_WEIGHT` | `0.20` | Scoring weight for field coverage |
| `DATAFORGE_SCORE_SOURCE_TRUST_WEIGHT` | `0.15` | Scoring weight for source trust |
| `DATAFORGE_SCORE_TYPE_INTEGRITY_WEIGHT` | `0.10` | Scoring weight for type integrity |
| `DATAFORGE_QUALITY_BASE_SCORE` | `0.3` | Base quality score for non-empty text values |
| `DATAFORGE_QUALITY_TEXT_LEN_THRESHOLD_1` | `4` | Text length bonus threshold 1 |
| `DATAFORGE_QUALITY_TEXT_LEN_THRESHOLD_2` | `20` | Text length bonus threshold 2 |
| `DATAFORGE_QUALITY_NOISE_PENALTY` | `0.6` | Penalty for noise phrases in identity fields |
| `DATAFORGE_QUALITY_SHORT_IDENTITY_PENALTY` | `0.2` | Penalty for short text in identity fields |
| `DATAFORGE_QUALITY_STATUS_LONG_PENALTY` | `0.4` | Penalty for long text in status fields |
| `DATAFORGE_QUALITY_STATUS_MISMATCH_PENALTY` | `0.2` | Penalty for status fields without known phrases |
| `DATAFORGE_QUALITY_PRESENT_FIELD_THRESHOLD` | `0.2` | Field quality above this counts as 'present' |
| `DATAFORGE_QUALITY_REQUIRED_MISSING_THRESHOLD` | `0.3` | Required field quality below this increments missing count |
| `DATAFORGE_QUALITY_REQUIRED_WEIGHT` | `1.2` | Weight multiplier for required fields |
| `DATAFORGE_QUALITY_PRESENCE_COHESION_THRESHOLD` | `0.3` | Presence vote below this triggers cohesion penalty |
| `DATAFORGE_QUALITY_PRESENCE_VOTE_WEIGHT` | `0.3` | Weight for presence vote in ensemble blend |
| `DATAFORGE_QUALITY_QUALITY_VOTE_WEIGHT` | `0.7` | Weight for quality vote in ensemble blend |
| `DATAFORGE_CONTACT_BOOST_MIN_RECORDS` | `2` | Minimum records to trigger page-level contact boosting |
| `DATAFORGE_CONTACT_BOOST_THRESHOLD` | `0.2` | Percentage of records with contacts below which boosting triggers |
| `DATAFORGE_CONTACT_VALID_PHONE_MIN_DIGITS` | `7` | Min digits for a valid phone number |
| `DATAFORGE_CONTACT_VALID_PHONE_MAX_DIGITS` | `15` | Max digits for a valid phone number |
| `DATAFORGE_SELECTOR_SNIPPET_MAX_CHARS` | `16000` | Max chars of HTML sent to LLM for selector discovery |
| `DATAFORGE_SELECTOR_MIN_TEXT_LEN` | `5` | Min text length for a node to be a data container |
| `DATAFORGE_SELECTOR_HEADING_FALLBACK_LEN` | `70` | Max length of text considered as heading fallback |
| `DATAFORGE_SELECTOR_FUZZY_MIN_WORDS` | `2` | Min words in example value for fuzzy matching |
| `DATAFORGE_SELECTOR_FUZZY_MAX_WORDS` | `5` | Max words in example value for fuzzy matching |
| `DATAFORGE_SELECTOR_FUZZY_MATCH_RATIO` | `0.7` | Min word match ratio for fuzzy example matching |
| `DATAFORGE_SELECTOR_CONTEXT_WINDOW_MAX_LEN` | `120` | Max characters for context window around fuzzy match |
| `DATAFORGE_SELECTOR_MIN_SEGMENT_LEN` | `3` | Min characters for extracted context segment |
| `DATAFORGE_SELECTOR_MEMORY_MAX_FAILURES` | `3` | Max consecutive failures before selector suspension |
| `DATAFORGE_REGEX_MAX_CONTAINERS` | `300` | Hard limit on containers scanned by regex fallback |
| `DATAFORGE_NOISE_COHESION_THRESHOLD` | `0.2` | Cohesion score below which a record is flagged as noise |
| `DATAFORGE_NOISE_MIN_VALUES_FOR_REPETITION_CHECK` | `3` | Identical fields required to trigger template-noise flag |
| `DATAFORGE_NOISE_SOCIAL_PLATFORM_THRESHOLD` | `3` | Social platforms seen before flagging as footer noise |
| `DATAFORGE_INSIGHT_MAX_FIELDS` | `8` | Max fields suggested by intent parser |
| `DATAFORGE_INSIGHT_SAMPLE_SIZE` | `20` | Number of records for dataset insight generation |
| `DATAFORGE_INSIGHT_TEMPERATURE` | `0.5` | Temperature for insight generation LLM calls |
| `DATAFORGE_URL_ANALYZER_MAX_FIELDS` | `30` | Max fields returned by the URL analyzer |
| `DATAFORGE_URL_ANALYZER_TEMPERATURE` | `0.5` | Temperature for URL analysis LLM calls |
| `DATAFORGE_URL_ANALYZER_TIMEOUT` | `120` | Max seconds for URL analysis endpoint |
| `DATAFORGE_AI_STRUCTURING_CHUNK_SIZE` | `15` | Records per chunk for LLM batch-cleaning |
| `DATAFORGE_AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES` | `5` | Stop AI cleaning after this many consecutive failures |
| `DATAFORGE_AI_CLEAN_TARGET_RECORDS` | `30` | Max top-scored records sent to AI cleaning |

## Job Execution & Crawl Policy

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_PER_URL_TIMEOUT_SECONDS` | `120` | Max seconds to spend scraping a single URL |
| `DATAFORGE_MAX_JOB_RUNTIME_SECONDS` | `1800` | Max total wall-clock seconds for one job |
| `DATAFORGE_AI_STRUCTURING_TIMEOUT_SECONDS` | `240` | Max seconds for the global AI structuring pass |
| `DATAFORGE_MAX_DISCOVERY_URLS` | `20` | Max URLs discovered per auto-discovery |
| `DATAFORGE_MAX_JOB_HISTORY` | `300` | Max completed/canceled jobs retained before pruning |
| `DATAFORGE_MAX_RECYCLE_BIN_HISTORY` | `300` | Max deleted jobs retained before pruning |
| `DATAFORGE_JOB_RESULTS_DISK_OFFLOAD_THRESHOLD` | `1000` | Record count above which job results are offloaded to disk |
| `DATAFORGE_JOB_MAX_PARALLEL_URLS` | `3` | Max URLs processed in parallel within a single job |
| `DATAFORGE_CRAWL_MAX_TOTAL_CONCURRENCY` | `10` | Absolute cap on global parallel fetches |
| `DATAFORGE_CRAWL_PER_DOMAIN_CONCURRENCY` | `2` | Max concurrent fetches per domain |
| `DATAFORGE_CRAWL_DEFAULT_DELAY_SECONDS` | `1.0` | Base delay between requests to same domain |
| `DATAFORGE_CRAWL_MAX_RETRIES_PER_DOMAIN` | `3` | Max consecutive failures before domain cooldown |
| `DATAFORGE_CRAWL_COOLDOWN_SECONDS` | `60` | Seconds to cool down a domain after max retries |
| `DATAFORGE_CRAWL_RESPECT_ROBOTS` | `true` | Whether to check robots.txt before fetching |
| `DATAFORGE_CRAWL_MAX_PAGES_PER_DOMAIN` | `50` | Max pages scraped from a single domain per job |
| `DATAFORGE_MAX_RECOVERY_ATTEMPTS` | `3` | Max recovery attempts per URL |
| `DATAFORGE_RECOVERY_TIMEOUT_MULTIPLIER` | `4` | Multiplier for per_url_timeout during recovery |
| `DATAFORGE_COST_PER_LLM_CALL` | `0.01` | Cost model: dollars per LLM call |
| `DATAFORGE_COST_PER_FETCH_MS` | `0.005` | Cost model: dollars per 1000ms of fetch time |
| `DATAFORGE_COST_PER_URL_SCRAPE` | `0.02` | Cost model: dollars per URL scraped |

## Failure Classification & Self-Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_CLASSIFY_HYDRATION_DOM_THRESHOLD` | `50` | DOM threshold for hydration failure detection |
| `DATAFORGE_CLASSIFY_EMPTY_PAGE_HTML_THRESHOLD` | `500` | HTML threshold for empty page classification |
| `DATAFORGE_CLASSIFY_LAZYLOAD_DOM_THRESHOLD` | `100` | DOM threshold for lazy load detection |
| `DATAFORGE_CLASSIFY_ANTIBOT_SCORE_THRESHOLD` | `0.6` | Anti-bot score threshold for classification |
| `DATAFORGE_CLASSIFY_LOW_SELECTOR_HIT_THRESHOLD` | `0.3` | Low selector hit rate threshold |
| `DATAFORGE_CLASSIFY_DECAY_RATE_THRESHOLD` | `0.5` | Decay rate threshold |
| `DATAFORGE_CLASSIFY_MALFORMED_DOM_RATIO` | `0.3` | Malformed DOM ratio threshold |
| `DATAFORGE_CLASSIFY_PARTIAL_EXTRACTION_FILL_RATE` | `0.5` | Partial extraction fill rate threshold |
| `DATAFORGE_CLASSIFY_FAILURE_PATTERN_THRESHOLD` | `3` | Consecutive failure pattern threshold |
| `DATAFORGE_CLASSIFY_HYDRATION_DELAY_INCREMENT` | `500` | Increment (ms) for progressive hydration delay |
| `DATAFORGE_CLASSIFY_HYDRATION_DELAY_MAX` | `10000` | Max hydration delay in ms |
| `DATAFORGE_EMPTY_RESPONSE_MIN_HTML_LEN` | `50` | Min HTML length for non-empty detection |
| `DATAFORGE_EMPTY_RESPONSE_MINIMAL_TEXT_LEN` | `100` | Minimal text length threshold |
| `DATAFORGE_EMPTY_RESPONSE_LOW_TEXT_LEN` | `300` | Low text length threshold |
| `DATAFORGE_EMPTY_RESPONSE_CONFIDENCE_THRESHOLD` | `0.5` | Confidence threshold for empty response |
| `DATAFORGE_EMPTY_PAGE_SIGNAL_CONFIDENCE` | `0.8` | Confidence threshold for empty page signal |
| `DATAFORGE_ZERO_RESULT_EMPTY_HTML_LEN` | `100` | HTML length below which = empty result |
| `DATAFORGE_ZERO_RESULT_JS_SHELL_HTML_LEN` | `1000` | HTML length threshold for JS shell detection |
| `DATAFORGE_SESSION_PARAM_NAME_CONFIDENCE` | `0.8` | Session detection confidence from param names |
| `DATAFORGE_SESSION_PARAM_VALUE_CONFIDENCE` | `0.7` | Session detection confidence from param values |
| `DATAFORGE_SESSION_PATH_HASH_CONFIDENCE` | `0.6` | Session detection confidence from path hashes |
| `DATAFORGE_SESSION_BOUND_CONFIDENCE_THRESHOLD` | `0.6` | Threshold above which URL is flagged as session-bound |

## Acquisition Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ACQUISITION_STANDARD_MAX_RETRIES` | `1` | Max retries for standard acquisition |
| `DATAFORGE_ACQUISITION_AGGRESSIVE_MAX_RETRIES` | `2` | Max retries for aggressive acquisition |
| `DATAFORGE_ACQUISITION_DEEP_SCAN_MAX_RETRIES` | `3` | Max retries for deep-scan acquisition |
| `DATAFORGE_ACQUISITION_AGGRESSIVE_TIMEOUT_MULT` | `1.5` | Timeout multiplier for aggressive mode |
| `DATAFORGE_ACQUISITION_DEEP_SCAN_TIMEOUT_MULT` | `2.0` | Timeout multiplier for deep-scan mode |
| `DATAFORGE_ACQUISITION_TELEMETRY_MAX_HISTORY` | `500` | Max telemetry history entries |
| `DATAFORGE_ACQUISITION_TELEMETRY_RECENT_DEFAULT` | `20` | Default count for recent telemetry queries |

## HTTP & Proxy

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_REQUEST_TIMEOUT` | `20` | Seconds before plain-HTTP fallback request times out |
| `DATAFORGE_ROBOTS_TIMEOUT` | `10.0` | Timeout for robots.txt fetching |
| `DATAFORGE_GEOCODER_TIMEOUT` | `10` | Timeout for reverse geocoding lookups |
| `DATAFORGE_USER_AGENT` | *(Chrome UA)* | User-agent string for HTTP requests |
| `DATAFORGE_MAX_RETRIES` | `2` | Number of retries for HTTP requests |
| `DATAFORGE_HTTP_BACKOFF_FACTOR` | `0.5` | Backoff multiplier for HTTP retries |
| `DATAFORGE_PROXY_ROTATION_ENABLED` | `false` | Enable proxy rotation for anti-bot resilience |
| `DATAFORGE_PROXY_LIST` | `""` | Comma-separated list of proxy URLs |
| `DATAFORGE_PROXY_ROTATION_FAILURE_THRESHOLD` | `5` | Rotate proxy after this many consecutive failures |
| `DATAFORGE_ANTIBOT_PLATFORM_MATCH_SCORE` | `0.6` | Score boost when platform matches expected pattern |
| `DATAFORGE_ANTIBOT_CLOUDFLARE_SCORE` | `0.45` | Score for Cloudflare server header detection |
| `DATAFORGE_ANTIBOT_AKAMAI_SCORE` | `0.55` | Score for Akamai server header detection |
| `DATAFORGE_ANTIBOT_HARD_BLOCK_THRESHOLD` | `0.8` | Anti-bot score above this means hard block |
| `DATAFORGE_ANTIBOT_STEALTH_ESCALATION_MEAN` | `0.4` | Mean score above which triggers stealth escalation |
| `DATAFORGE_ANTIBOT_HARD_BLOCK_DELAY` | `30` | Seconds to delay after a hard block detection |
| `DATAFORGE_ANTIBOT_MEDIUM_CHALLENGE_DELAY` | `5` | Seconds to delay after a medium challenge detection |
| `DATAFORGE_ANTIBOT_COOKIE_MAX_AGE_HOURS` | `24` | Max age in hours before cookie refresh required |

## LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_LLM_TIMEOUT` | `45` | Default timeout for LLM JSON/text calls |
| `DATAFORGE_LLM_FAST_TIMEOUT` | `12` | Fast-path timeout for throughput-sensitive LLM calls |
| `DATAFORGE_LLM_SELECTOR_TIMEOUT` | `30` | Timeout for selector discovery LLM calls |
| `DATAFORGE_INSIGHT_TIMEOUT_SECONDS` | `25` | Timeout for insight generation calls |
| `DATAFORGE_LLM_TEMPERATURE` | `0.1` | Default LLM temperature for JSON calls |
| `DATAFORGE_LLM_FAST_TEMPERATURE` | `0.0` | Temperature for fast-path JSON calls |
| `DATAFORGE_LLM_TEXT_TEMPERATURE` | `0.4` | Temperature for free-form text calls |
| `DATAFORGE_LLM_MAX_ATTEMPTS` | `2` | Retries for LLM API calls |
| `DATAFORGE_LLM_BACKOFF_SECONDS` | `0.8` | Base backoff for LLM retries |
| `DATAFORGE_LLM_VALIDATE_JSON` | `true` | Validate LLM JSON output against expected schema |
| `DATAFORGE_LLM_VALIDATION_MAX_RETRIES` | `2` | Max retries for malformed LLM JSON |
| `DATAFORGE_GROQ_DEFAULT_MODEL` | `llama-3.3-70b-versatile` | Default model for Groq LLM calls |
| `DATAFORGE_GROQ_FALLBACK_MODEL` | `llama-3.1-8b-instant` | Fallback model when default Groq model fails |
| `DATAFORGE_GROQ_API_ENDPOINT` | `https://api.groq.com/...` | Groq API endpoint for LLM calls |
| `DATAFORGE_POLLINATIONS_API_ENDPOINT` | `https://text.pollinations.ai/...` | Pollinations AI endpoint |
| `DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS` | `false` | Allow unauthenticated public LLM fallbacks |
| `DATAFORGE_G4F_JSON_MODEL` | `gpt-4o-mini` | Model for g4f JSON fallback calls |
| `DATAFORGE_G4F_TEXT_MODEL` | `gpt-4o` | Model for g4f text fallback calls |
| `DATAFORGE_SANDBOX_DISABLED` | - | (Historical) Bypass the LLM sandbox for research modules. Replaced by targeted `@pytest.mark.network` / `@pytest.mark.integration` markers in tests.

## Additional Security

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ALERT_WEBHOOK_URL` | - | URL to send webhook alerts for anti-bot level shifts |
| `DATAFORGE_CSP_REPORT_ONLY` | `true` | Attach a report-only Content-Security-Policy header |
| `DATAFORGE_SESSION_MAX_AGE` | `86400` | Session cookie max age in seconds (default 24h) |
| `DATAFORGE_RATE_LIMIT_JOB_CREATE` | `10/minute` | Rate limit for job creation endpoint |
| `DATAFORGE_RATE_LIMIT_DISCOVER` | `20/minute` | Rate limit for discovery endpoint |
| `DATAFORGE_METRICS_ENABLE_HISTOGRAMS` | `true` | Enable request duration/operation latency histograms |
| `DATAFORGE_METRICS_HISTOGRAM_BUCKETS` | `0.01,0.05,...` | Comma-separated bucket boundaries for duration histograms |
| `DATAFORGE_EMAIL_BLOCKED_DOMAINS` | `example.com,test.com,localhost` | Comma-separated email domains to reject |

## Access Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ACCESS_LOG_ENABLED` | `true` | Master switch for the structured HTTP access-log middleware. Set to `0`/`false`/`no`/`off` to disable the per-request log line (method, path, status, latency, client IP, user-agent, request id). Read directly by `app/access_log.py`. |

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_LOG_FORMAT` | `json` | Logging output format: `json` (structured lines for log aggregators like Loki/ELK/CloudWatch) or `text` (human-readable plain text). Invalid values fall back to `json`. Read directly by `app/logging_config.py`. |
| `DATAFORGE_LOG_LEVEL` | `INFO` | Application-wide log level. Recognised values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; invalid values fall back to `INFO`. Read directly by `app/logging_config.py`. |

## LLM Bridge

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_LLM_CIRCUIT_ENABLED` | `true` | Master switch for the LLM cascade circuit breaker. Disable (set to `false`) when running unit tests that intentionally exhaust cascades for failure-path validation. Configured in `app/config/_communication.py`. |
| `DATAFORGE_LLM_RAISE_ON_FAILURE` | `false` | When `true`/`1`/`yes`/`on`, the LLM bridge public functions raise `LLMCascadeExhausted` on cascade exhaustion instead of silently returning empty results. Defaults to silent (legacy). Read directly by `app/utils/llm_bridge_settings.py`. |

## HTML Size Cap

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_MAX_HTML_BYTES` | `10485760` (10 MB) | Hard upper bound on HTML payload size accepted before parsing. Payloads exceeding this raise `HTMLSizeExceeded` (or are truncated if `must_truncate=True`). Negative or non-numeric values fall back to 10 MB. Read directly by `app/utils/html_size.py`. |

## Paths & State

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_STATE_DIR` | `""` | Base directory for all mutable runtime state |
| `DATAFORGE_AUDIT_LOG_DIR` | `""` | Override for audit log directory |
| `DATAFORGE_DOMAIN_INTELLIGENCE_PATH` | `data/domain_intelligence.json` | Path to domain intelligence file |
| `DATAFORGE_SELECTOR_MEMORY_PATH` | `data/selector_memory.json` | Path to selector memory file |
| `DATAFORGE_SELECTOR_PROFILES_DIR` | `profiles` | Directory for selector profile definitions |
| `DATAFORGE_TELEMETRY_STREAM_MAXLEN` | `1000` | Max length of telemetry stream |
| `DATAFORGE_TELEMETRY_RECORD_EXTRACTION` | `true` | Emit per-URL scrape telemetry events |
| `DATAFORGE_MOTIF_MIN_COOCCURRENCE` | `2` | Minimum co-occurrence for motifs |
| `DATAFORGE_DOMAIN_INTELLIGENCE_SMOOTHING_ALPHA` | `0.3` | Smoothing alpha for domain intelligence |
| `DATAFORGE_GOSSIP_PROPAGATION_INTERVAL` | `60` | Gossip propagation interval in seconds |
| `DATAFORGE_NODE_ID` | `node-1` | Unique identifier for this node/worker |
| `DATAFORGE_SHARD_ID` | `shard-1` | Unique identifier for the sharded workload |
| `DATAFORGE_WORKFLOW_BACKEND` | `json` | Workflow storage backend (`json`, `sqlite`, `postgres`) |
| `DATAFORGE_PG_MIN_CONN` | `1` | Postgres pool minimum size |
| `DATAFORGE_PG_MAX_CONN` | `10` | Postgres pool maximum size |

## Notification Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TELEGRAM_NOTIFY_ON_TEST_START` | `true` | Send notification when test suite starts |
| `DATAFORGE_TELEGRAM_NOTIFY_ON_TEST_END` | `true` | Send notification when test suite ends |
| `DATAFORGE_TELEGRAM_NOTIFY_ON_TEST_FAILURE` | `true` | Send notification on individual test failures |
| `DATAFORGE_TELEGRAM_NOTIFY_ON_CRITICAL_ERROR` | `true` | Send notification on critical application errors |
| `DATAFORGE_TELEGRAM_API_BASE` | `https://api.telegram.org` | Telegram Bot API base URL |

## Discovery & Source Trust

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_QUEUE_BACKEND` | `sqlite` | Worker queue backend: `sqlite` or `postgres` |
| `DATAFORGE_BLOCKED_DISCOVERY_DOMAINS` | `quickfinds.org` | Comma-separated root domains excluded from discovery |
| `DATAFORGE_DISCOVERY_SOCIAL_DOMAINS` | *(long list)* | Comma-separated social root domains for source classification |
| `DATAFORGE_DISCOVERY_SEARCH_DOMAINS` | `google.com,...` | Comma-separated search engine domains for source classification |
| `DATAFORGE_SOURCE_TRUST_OFFICIAL` | `0.92` | Default trust score for official domains |
| `DATAFORGE_SOURCE_TRUST_DIRECTORY` | `0.62` | Default trust score for directory domains |
| `DATAFORGE_SOURCE_TRUST_SOCIAL` | `0.5` | Default trust score for social media domains |
| `DATAFORGE_SOURCE_TRUST_SEARCH` | `0.35` | Default trust score for search engine results |

## Rate Limit Pruning

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_RATE_LIMIT_PRUNE_INTERVAL` | `3600` | Seconds between background prunes of the rate_limits table |

## Production Validation

Before deploying to production, validate environment:

```bash
# Run production environment checker
python3 scripts/check_prod_env.py

# Run security validator
python3 -c "from app.utils.prod_security_validator import validate_production_credentials; validate_production_credentials()"
```

## Security Notes

1. **Never commit secrets** - Use environment variables or secrets manager
2. **Rotate keys regularly** - Especially `DATAFORGE_SESSION_SECRET` and `DATAFORGE_ADMIN_API_KEY`
3. **Use HTTPS in production** - Set `DATAFORGE_ENV=production`
4. **Validate on startup** - Use `scripts/check_prod_env.py` before deployment
