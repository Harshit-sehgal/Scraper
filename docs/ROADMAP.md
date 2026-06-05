# Roadmap

This document tracks the phased plan for DataForge (`Harshit-sehgal/Scraper`) and
the current state of each workstream. It is a living artifact — last updated
after the deep-research remediation pass (2026-06).

## Legend

- **Status** — what is true today.
- **Next** — the smallest concrete deliverable that moves the workstream
  forward.
- **Done in this pass** — items closed by the deep-research remediation.

## Workstreams

### W1 — Driver portability (psycopg 3) — done in this pass

- **Status:** `psycopg3_repository.py` ships alongside `postgres_repository.py`.
  The factory in `app/storage_interface.py` selects the driver via
  `DATAFORGE_PG_DRIVER=psycopg3`. All repository contract methods
  (`get_job`, `list_job_summaries`, `read_events`, `list_recycle_summaries`)
  are implemented on all three backends (SQLite, psycopg2, psycopg3) and
  pinned by `test_psycopg3_repository.py` (9 tests) +
  `test_targeted_reads.py` (10 tests) + `test_repository_parity.py`
  (13 SQLite + 5 Postgres-skipped). Pool sizing is configurable via
  `DATAFORGE_PG_MIN_CONN` / `DATAFORGE_PG_MAX_CONN` (defaults: 1 and 10;
  clamped to `[1, 1000]`; garbage-tolerant).
- **Next:** ship behind the env flag in staging, watch `dataforge_repo_query_latency_seconds`
  for regressions, then flip the default in a future minor release.
- **Done in this pass:** backend module, contract tests, factory branch, observability
  hook, `list_recycle_summaries` abstract + SQLite/psycopg2/psycopg3 impls,
  pool sizing knobs (`Settings.PG_MIN_CONN` / `Settings.PG_MAX_CONN`),
  parity tests for the recycle-summaries contract, removal of
  `psycopg2-binary` from the production image.

### W2 — Storage split (jobs/results/events/idempotency) — done in this pass

- **Status:** v4 schema adds `job_results`, `job_events`, `idempotency_keys`
  companion tables. Dual-write preserves the legacy `Job.results` / `Job.logs`
  JSON columns for back-compat. `psycopg3_repository.read_events` mirrors the
  psycopg2 reader. `list_recycle_summaries()` is implemented on all three
  backends (SQLite, psycopg2, psycopg3) and pinned by parity tests. See
  `docs/STORAGE_SPLIT.md` for the v4 → v5 → v6 cutover plan.
- **Next:** v5 release drops the legacy JSON columns once the metrics show that
  no client reads `Job.results` / `Job.logs` directly. v6 release migrates the
  heavy payloads to JSONB.
- **Done in this pass:** v4 schema, dual-write helpers, readers, parity tests
  (`test_storage_split_v4.py`, 10 tests), cutover plan doc, recycle-summaries
  contract on all three backends.

### W3 — Idempotency keys for `POST /api/jobs` — done in this pass

- **Status:** `Idempotency-Key` header (max 128 chars) is honoured; replays
  return the original `job_id` with `idempotent_replay: true`. Backed by the
  `idempotency_keys` companion table (no FK to `jobs`; key survives job
  hard-delete). Helpers in `job_store.py`: `lookup_idempotency_key`,
  `record_idempotency_key`, `prune_idempotency_keys(older_than_days=7)`. Pinned
  by `test_idempotency_keys.py` (6 tests).
- **Next:** tighten conflict resolution (return 409 on payload-fingerprint
  mismatch). Add pruning cron / operator CLI.
- **Done in this pass:** header support, storage helpers, tests, docs.

### W4 — Dependency hygiene — done in this pass

- **Status:** `requirements.txt` and `requirements-dev.txt` are single-line
  `-r` wrappers pointing at the lock files. `requirements.lock.txt` and
  `requirements-dev.lock.txt` are committed and CI-validated via
  `validate_dependency_bounds.py`. All 9 GitHub workflows + `Dockerfile` +
  `scripts/start.sh` install from the lock files. The wrapper contract is
  pinned by `test_requirements_wrapper_contract.py` (7 tests).
- **Next:** add Dependabot for the lock files (rebase-only, weekly).
- **Done in this pass:** lockfile split, wrapper contract test, workflow /
  docs alignment.

### W5 — CI hardening — done in this pass

- **Status:** `ci.yml` runs the fast lane on every PR. New `image-build.yml`
  builds the multi-arch image on `main` + tags and signs with cosign.
  Optional lanes (`postgres-tests.yml`, `browser-e2e.yml`, `golden-dataset.yml`,
  `load-test.yml`, `optional-suites.yml`) run on schedule / manual dispatch.
  Coverage report + route-inventory are uploaded as artifacts. Docs lint
  enforces 59 route families against `docs/API.md`.
- **Next:** enable required status checks; wire the image-build lane to GHCR
  with provenance attestation.
- **Done in this pass:** image-build lane, coverage + route-inventory
  artifacts, docs lint scope extended, lanes split.

### W6 — Observability (Prometheus + Grafana + Alerts) — done in this pass

- **Status:** Grafana dashboard (`grafana/dashboards/dataforge_overview.json`)
  covers 22 panels across 8 KPI stats, 10 timeseries graphs, and 4 pie charts.
  All 14 supported Prometheus metrics are surfaced: system health,
  request latency, memory, LLM usage, anti-bot classifications (9 platforms),
  extraction methods, browser launches, export outcomes, SSRF rejects by
  reason, CSP violations by directive, repo query latency quantiles, and
  queue depth. Prometheus alert rules (`prometheus_alerts.yml`) define
  12 alert rules: 3 critical (API down, DB errors, browser failures),
  8 warning (queue backlog, job failures, latency, anti-bot blocks, export
  failures, SSRF blocks, repo latency degradation, extraction method
  anomaly), and 1 info (CSP violation rate). Alertmanager
  (`alertmanager.yml`) routes alerts by severity to email and Slack with
  3 inhibition rules and rate-limiting varying by severity (1h critical,
  4h warning, 24h info). See W14 for Alertmanager details.
- **Next:** raise Postgres backend coverage floors from 24% to 40% in
  the next minor release. Tighten CSP to enforce mode once the dashboard
  shows zero violations for at least one release cycle.
- **Done in this pass:** 22-panel Grafana dashboard, 12 Prometheus alert
  rules, Alertmanager config + docker-compose integration, Severity-based
  routing + inhibition, metrics collectors + call-site wiring, metric
  tests (21 + 10 tests), CSP report-only middleware.

### W7 — Security & TLS — done in this pass

- **Status:** `nginx.conf` enforces HTTPS first; HTTP redirects 301 → HTTPS
  (preserves ACME challenge path); HSTS only on the TLS listener. The
  dev-only HTTP block is commented with an explicit "no HSTS" note. Frontend
  API key is module-scope memory only (no `sessionStorage` /
  `localStorage`). SSRF: **public** httpx transport wrappers (the
  PRIMARY enforcement layer, on `httpx.AsyncBaseTransport.handle_async_request`
  / `httpx.BaseTransport.handle_request`) + private httpcore backend swap
  (SECONDARY defense-in-depth against DNS rebinding) + `verify_ssrf_self_check()`
  hard-fails in prod/staging. The public-API wrapper does not depend on
  httpx internals: if `_pool._network_backend` is replaced by a hostile
  backend, the public wrapper still blocks the request at request time.
  CSP report-only header attached to every response via
  `csp_report_only_middleware`; browser reports POSTed to
  `POST /api/system/csp-violations` (unauthenticated on purpose, body-size
  capped, rate-limited). See `docs/TLS_DEPLOYMENT.md` and
  `docs/DASHBOARD_AUTH.md`.
- **Next:** HTTP-only + SameSite=Strict cookie option for the v2 dashboard
  auth (replaces the in-memory key). Tighten the report-only CSP once the
  dashboard shows zero violations for at least one release cycle.
- **Done in this pass:** nginx posture, frontend key guard, SSRF self-check,
  operator verification checklist, CSP report-only middleware + violation
  endpoint + metrics gauge, `CSP_REPORT_ONLY` setting toggle,
  public-API SSRF transport wrapper promoted to PRIMARY layer
  (`get_safe_async_client` / `get_safe_client` stack the public wrapper
  on top of the private-injection transport), `test_ssrf_public_transport.py`
  (9 tests) pins the new layout, prod image no longer carries
  `psycopg2-binary` (dev-only opt-in for the legacy `PostgresJobRepository`).

### W8 — Config & observability hygiene — done in this pass

- **Status:** `globals.CONFIG` is rebuilt from `settings` in `lifespan()`
  (no inline `CONFIG.update` calls). Rate-limit DB auto-promotion runs as a
  pydantic `model_validator(mode="after")`. Worker queue mode is a dynamic
  env-var property (toggle via `DATAFORGE_WORKER_QUEUE`, not
  `monkeypatch.setattr`).
- **Next:** retire the `globals.CONFIG` dict once the lifespan is the only
  writer; expose `config_view()` as the single read API.
- **Done in this pass:** `globals.config_view()`, `rebuild_config_from_settings()`,
  rate-limit promotion test, worker queue dynamic property.

### W9 — Docs drift — done in this pass

- **Status:** `docs_lint.py` tracks 8 `/api/*` prefix families (59 routes
  match). `scripts/route_inventory.py` regenerates the route table by
  introspecting the live FastAPI app. `docs/API.md` covers all route families
  (jobs, recycle_bin, discover, schema, url, scraper, operator, system).
- **Next:** auto-commit the regenerated route table in CI.
- **Done in this pass:** docs lint scope, route inventory script, API.md
  expansion.

### W10 — Test strategy — done in this pass

- **Status:** 2891 tests pass, 87 skipped (fast lane). The optional
  postgres / browser / golden-dataset lanes are opt-in.
- **Status details:**
  1. **Repository parity tests** — `test_repository_parity.py` provides
     the contract specification: same test bodies run against
     `SQLiteJobRepository` and `PostgresJobRepository` (testcontainers
     backend, gated by `--run-postgres`). The Postgres variants are
     skipped by default; enable when Docker is available. Includes the
     `list_recycle_summaries` contract (4 SQLite + 1 Postgres).
  2. **Benchmark governance** — `scripts/live_benchmark.py` now exits
     with code 78 (skipped) when `DATAFORGE_RUN_LIVE_BENCHMARKS` is not
     set to `"1"`. `scripts/run_benchmarks.sh` always runs the
     in-corpus unit benchmarks (CI-safe) and only runs the live
     benchmarks when the flag is set. Pinned by
     `test_benchmark_governance.py` (4 tests).
  3. **Public-API SSRF transport wrapper tests** —
     `test_ssrf_public_transport.py` (9 tests) pins the primary SSRF
     enforcement layer: the wrapper subclasses `httpx.AsyncBaseTransport` /
     `httpx.BaseTransport` only, blocks private IPs at request time
     (no `_pool` access), and survives a hostile `_pool._network_backend`.
  4. **Postgres pool sizing tests** — `test_pg_pool_settings.py`
     (11 tests) pins the unified `Settings.PG_MIN_CONN` /
     `Settings.PG_MAX_CONN` properties (clamped to `[1, 1000]`,
     garbage-tolerant, maxconn ≥ minconn invariant).
  5. **Coverage floors for Postgres backends** — still at 24.0%; will
     be raised in tandem with parity tests once the Postgres backend
     parity suite runs in regular CI.
- **Next:** raise Postgres backend coverage floors from 24% to 40% in
  the next minor release.
- **Done in this pass:** storage split tests, idempotency tests, summary
  DTO contract test, observability wiring tests, dependency wrapper
  contract test, hot-path regression test, TLS posture test, dashboard
  auth guard, CSP report-only test, benchmark governance test,
  repository parity tests, public-API SSRF transport tests, pool
  sizing tests, `list_recycle_summaries` parity tests.

### W11 — Coverage — done in this pass

- **Status:** global `fail_under=60`; per-module floors enforced by
  `check_coverage_floors.py`; coverage report uploaded as a CI artifact.
  Global coverage after the remediation pass: **78.2%**. Per-module floors:
  `url_safety` 60, `storage_interface` 70, `routers/jobs` 70,
  `routers/exports` 60, `lifespan` 40, `psycopg3_repository` 24,
  `postgres_repository` 24.
- **Next:** raise the Postgres backend floors once W10 parity tests land.
- **Done in this pass:** global floor, per-module floors, CI artifact.

### W12 — DR / failover — next quarter

- **Status:** `scripts/backup_postgres.sh` and `scripts/restore_postgres.sh`
  exist; no drill has been run end-to-end.
- **Next:** schedule a monthly backup/restore drill against a staging
  cluster; capture the time-to-recover in `INCIDENT_RUNBOOK.md`.
- **Done in this pass:** none (carry-over).

### W13 — Release engineering — next quarter

- **Status:** `image-build.yml` builds the image on `main` + tags; no cosign
  signing yet, no SBOM attestation. SBOM generation runs in CI via `syft`.
- **Next:** cosign signing, SLSA provenance, GHCR publish.
- **Done in this pass:** image-build lane, SBOM generation in CI.

### W14 — Alertmanager — done in this pass

- **Status:** Full Alertmanager configuration (`alertmanager.yml`) deployed
  as a Docker Compose service (`prom/alertmanager:v0.27.0`) in the production
  stack. Routes alerts from the 12 Prometheus rules by severity:
  - **Critical** (3 rules): email + Slack (`#alerts-critical`), repeats
    every 1h, `continue: true` for redundant email delivery
  - **Warning** (8 rules): Slack only (`#alerts-warning`), repeats every 4h
  - **Info** (1 rule): Slack only (`#alerts-info`), repeats every 24h,
    `send_resolved: false`
  3 inhibition rules suppress symptomatic alerts when root causes fire
  (API down → all warnings, DB errors → repo latency, critical →
  extraction anomaly). Prometheus configured with `alerting:` block
  pointing at `alertmanager:9093` with `api_version: v2` and labeldrop
  relabel. Credentials injected via Go template env vars (`{{ .Env.VAR }}`).
  Graceful handling of missing SMTP/Slack env vars (logs warning, skips
  notifications).
- **Next:** add pushover / pagerduty receiver for critical alerts.
  Wire up alertmanager_data volume to backup schedule.
- **Done in this pass:** alertmanager.yml, Prometheus alerting block,
  docker-compose.prod.yml service, severity-based routing, inhibition
  rules,  env var templating.

### W15 — Frontend tooling (CSS lint) — done in this pass

- **Status:** stylelint@^16 with stylelint-config-standard@^36 enforces CSS
  quality in CI. Config (`package.json`, `.stylelintrc.json`) tuned for the
  project: modern color notation (`rgb(0 0 0 / 0.35)`), relaxed selector
  patterns (dotted class names like `.gap-0.5`), no blocking specificity
  or single-line declaration checks. Runs in `lint-type-checks` CI job
  with npm caching. The 2,312-line `frontend/styles.css` passes with
  0 errors after auto-fixing color notation to modern and removing a
  duplicate `.shortcut-hint` selector.
- **Next:** add Prettier or dprint for JS formatting parity.
- **Done in this pass:** package.json, .stylelintrc.json, CI job with
  npm cache, CSS fixes (modern notation, duplicate selector removal).

### W16 — Batch export API — done in this pass

- **Status:** `POST /api/exports/batch` accepts up to 50 job IDs and exports
  combined results in CSV, JSON, or Excel format. Supports `flatten=True`
  (single combined output with `_source_job` column) and `flatten=False`
  (separator rows for CSV, `exports` object for JSON, one sheet per job
  for Excel). Fieldnames are computed as the union of all fields across
  all jobs. Empty-result jobs are silently skipped. Fails fast on missing
  job IDs (404) or no results at all (400). Reuses existing helpers
  (`_strip_system_fields`, `_flat_row`, `_safe_cell`). Pinned by
  20 tests in `test_exports_router.py`.
- **Next:** add support for streaming large disk-backed datasets in pages
  (currently loads all results at once to union fieldnames).
- **Done in this pass:** `BatchExportRequest` model, `_batch_csv`/
  `_batch_json`/`_batch_xlsx` format handlers, per-job result
  collection with union fieldnames, 20 tests covering all formats,
  both flatten modes, and error paths.

### W17 — Per-IP rate limiting — done in this pass

- **Status:** Rate limiting upgraded from a flat per-IP model to a
  **dual-layer** approach: Tier 1 (aggregate global cap, 600/minute)
  controls total throughput across all clients combined; Tier 2 (per-IP
  fair-share cap, 100/minute) ensures no single client monopolises the
  API. A request must pass both tiers to proceed. Configurable via
  `DATAFORGE_RATE_LIMIT_PER_IP` (env var) and toggleable via
  `DATAFORGE_RATE_LIMIT_PER_IP_ENABLED`. In production/staging, counters
  auto-promote to the shared `rate_limits` database table for
  multi-worker consistency. Pinned by 25 tests.
- **Next:** add Prometheus counters for global vs per-IP rate limit hits.
  Expose `get_stats()` at `/api/system/rate-limit-stats`.
- **Done in this pass:** `RATE_LIMIT_PER_IP` and `RATE_LIMIT_PER_IP_ENABLED`
  settings, dual-layer middleware dispatch (aggregate aggregate + per-IP),
  `_get_aggregate_key` / `_get_per_ip_key` key builders,
  `_get_or_create_counter` helper, refactored `_build_429_response` and
  `_add_rate_limit_headers`, middleware wiring in `middlewares.py`,
  5 new tests (stats, counter selection, key distinctness).

### W18 — Documentation (export + rate limiting + setup) — done in this pass

- **Status:** `docs/API.md` documents the batch export endpoint with format
  options, flatten modes, error codes, and a curl example — plus a new Rate
  Limiting section explaining the dual-layer tiers, response headers, safe IP
  extraction, and DB-backed promotion. `.env.example` and `backend/.env.example`
  include `RATE_LIMIT_GLOBAL`, `RATE_LIMIT_PER_IP`, `RATE_LIMIT_PER_IP_ENABLED`,
  and `RATE_LIMIT_DB_BACKED`. `docs/SETUP.md` has a new Rate Limiting section
  explaining defaults and production auto-promotion.
- **Next:** auto-generate the API doc route table from the live FastAPI app
  and commit the diff on `main`.
- **Done in this pass:** API.md sections, env example files, SETUP.md note.

## Phased plan

| Phase | Window | Theme | Items |
|-------|--------|-------|-------|
| Late Q2 | 2026-06 | Hygiene + hard gates | W1–W11 (deep-research pass) |
| Late Q2 | 2026-06 | Observability + tooling | W6 (Grafana + alerts), W14 (Alertmanager), W15 (CSS lint) |
| Late Q2 | 2026-06 | API + infrastructure | W16 (Batch export), W17 (Per-IP rate limiting), W18 (Docs) |
| Q3 | 2026-07 → 2026-09 | Storage + coverage | v5 column drop, raise Postgres coverage floors to 40% |
| Q4 | 2026-10 → 2026-12 | DR + release engineering | W12 (DR drills), W13 (cosign, GHCR) |
| Q1 2027 | 2027-01 → 2027-03 | Storage split v6 + v2 dashboard auth | v6 JSONB, HTTP-only cookie auth |

## Out-of-scope

- Replacing the FastAPI surface with gRPC.
- Multi-region active/active.
- On-prem air-gapped install story.
