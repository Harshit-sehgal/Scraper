# Changelog

All notable changes to DataForge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Circuit breaker pattern for fault tolerance (`backend/app/utils/circuit_breaker.py`)
- Retry logic with exponential backoff (inline across `backend/app/llm_bridge.py` and webhook delivery)
- Usage ledger and quota system (`backend/app/utils/usage_ledger.py`)
- Extraction quality metrics tracker (`backend/app/utils/extraction_metrics.py`)
- Security tests for input validation and auth (`backend/tests/test_security.py`)
- Coverage reporting with pytest-cov
- Documentation verification script
- **Feat 10**: Webhook delivery retry with exponential backoff (3 attempts, 1s/5s/25s delays) and optional tenant isolation guard in `backend/app/services/webhook_delivery.py`
- 14 isolated unit tests for job mutation service (SELECTOR-001, STATE-001)
- 36 storage mapper unit tests (STORAGE-001 partial)
- 6 fixture-backed characterization tests for selector-discovery primitives
- 13 SQLite repository unit tests for 7 previously untested methods
- E2E Playwright test suite (`frontend/e2e/`) — auth, jobs, views, billing
- Synthetic alert drill tooling (`scripts/run_alert_delivery_drill.py`)
- Reproducible load test tooling (`scripts/run_load_test.py`) with JSON artifacts
- Variant extraction module (`backend/app/variant_extractor.py`)
- Thread-safe singletons for acquisition telemetry, crawl state, self-tuning controller, policy engine
- 26 discovery-quality tests for refactored components (lifespan, html_utils, scraper, browser_pool)
- CI/CD pipeline (`.github/workflows/ci.yml`)
- Captcha timeout and fallback tests
- 74 new E2E tests (jobs, API keys, billing, audit, retention, settings, workflows, auth-profiles, monitoring, invitations)
- 6 E2E tests for review API routes (list/get/approve/reject)
- 3 E2E tests for batch export route (`POST /api/exports/batch`)

### Changed

- Refactored `lifespan.py` (272→36 lines), `html_utils.py` `fetch_page_content` (367→63 lines), `scraper.py` `scrape_url` (352→296 lines), `browser_pool.py` `get_context` (320→31 lines)
- Tightened Playwright cleanup handlers across 6 source files to catch `Error` base class
- Centralized auth through `app.utils.rbac.resolve_auth_context` (eliminated inline auth checks)
- SaaS delete endpoints (`DELETE /api/saas/orgs/{id}`, `DELETE /api/saas/projects/{id}`) now backed by store methods
- Moved `CURRENT_AUP_VERSION` from `app.saas/router.py` to `app.saas/__init__.py` (circular import fix)
- Frontend esbuild bundler with code splitting (106 KB CSS < 200 KB threshold)
- Production Docker Compose uses split-volume layout (read-only root filesystem)
- Updated route inventory and auth matrix generators

### Fixed

- Documentation mismatches between code and docs
- Frontend loading states and error handling
- Security headers in production
- Playwright `TargetClosedError`/`TimeoutError` not caught by narrow exception tuples (6 source files)
- Circular import in `CURRENT_AUP_VERSION` resolution
- 18 stale MEDIUM-gap test stubs committed broken — deleted
- 44 stale AI-session artifacts deleted
- Dangling `patch_status` string ref in research registry
- CSP violations, metric-health double-write, dead export, unused CSS
- 6 stale markdown truth files deleted (surviving docs point at `docs/AGENT_TRUTH.md`)
- 8 stale backup branches deleted (all verified ancestor of main)
- `test_get_usage_returns_defaults_with_no_activity` — non-deterministic user_id race
- 5 stale `worktree-agent-*` branches deleted
- `backend/tests/helpers.py` — orphaned dead code (zero imports) deleted
- 3 review routes had `unknown_tenant` scope — added to `TENANT_SCOPED_PREFIXES`
- 41 undocumented `.env.example` vars — documented in `docs/CONFIG_AUDIT.md`
- `coverage/` and `artifacts/frontend_review/` added to `.gitignore` (35 PNGs, 3.7 MB removed from tracking)

### Removed

- Pure-garbage assets: `frontend/fonts/JetBrainsMono-Variable.woff2` (102 B ASCII, not a font), `frontend/dist/` (vite build output), `shelved/` (abandoned `forge_kernel`)
- Dead-code with zero call-sites: `frontend/js/error-boundary.js`, `backend/tests/manual_run_manual_test.py`, `backend/tests/test_page.html`, `backend/tests/test_semantic_state.json.lock`, `verify_compile.py` (root), `CODE_REVIEW_BUGS.md`, `CODE_SCAN_RESULTS.md`
- 3 orphaned research scripts in `backend/tests/` (never collected by pytest)
- Stale docs: `PROJECT_STATUS.md`, `docs/CURRENT_STATUS.md`, `docs/PRODUCTION_READINESS.md`, `docs/ROADMAP.md`, `docs/REFACTOR_PLAN.md`, `scripts/generate_status.py`, `Instructions_for_ai/` directory
- 8 merged backup branches
- 5 stale `worktree-agent-*` branches
- `backend/tests/helpers.py` (orphaned, zero imports)

## [0.1.0] - 2026-06-10

### Added

- Initial release of DataForge
- FastAPI backend with Playwright web extraction
- Frontend dashboard with real-time updates
- PostgreSQL and SQLite support
- Rate limiting (dual-layer)
- Session authentication
- API key authentication
- Export functionality (CSV, JSON, Excel)
- Job management (create, cancel, delete)
- Recycle bin for soft deletes
- Worker queue for async jobs
- Circuit breaker pattern
- Retry logic with exponential backoff
- Usage ledger and quota system
- Extraction quality metrics
- Error boundary and loading states
- Security tests
- Comprehensive documentation

### Security

- CSP headers configured
- HSTS enabled in production
- Rate limiting implemented
- Input validation added
- SQL injection protection
- XSS protection

## [0.0.1] - 2026-05-01

### Added

- Project initialization
- Basic structure
- Initial documentation

[Unreleased]: https://github.com/your-org/dataforge-scraper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/dataforge-scraper/releases/tag/v0.1.0
[0.0.1]: https://github.com/your-org/dataforge-scraper/releases/tag/v0.0.1
