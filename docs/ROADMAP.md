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

### W6 — Observability (Prometheus) — done in this pass

- **Status:** new gauges exported from `/metrics`:
  - `dataforge_extraction_method_total{method}`
  - `dataforge_anti_bot_classifications_total{classification}`
  - `dataforge_export_outcomes_total{format,outcome}`
  - `dataforge_browser_launch_total{outcome}`
  - `dataforge_ssrf_rejects_total{reason}`
  - `dataforge_repo_query_latency_seconds{quantile=0.5|0.95}`
  - `dataforge_csp_violations_total{directive}`
- **Call-site coverage:** SSRF reject wired in `url_safety.validate_public_http_url`,
  browser launch outcomes wired in `browser_pool.py`, export outcomes wired
  around the csv/json/excel routes, CSP violations wired to
  `POST /api/system/csp-violations`. Extraction method + anti-bot
  classification call sites wired at the scraper-engine convergence
  points (`scraper.py`), `failure_classification._build_classification`,
  `zero_result_classifier._build`, and the recovery integration's
  `ANTI_BOT_BLOCKED` branch. Platform label resolved by
  `detect_anti_bot_platform()`.
- **Next:** build Grafana dashboard; add Prometheus alert rules (queue
  depth, browser failure rate, SSRF reject rate, CSP violation rate).
- **Done in this pass:** metric helpers, basic + prometheus-client paths,
  call-site wiring for SSRF / browser / exports / CSP, scraper-engine
  convergence points wired for extraction method + anti-bot, platform
  label resolution, tests (`test_metrics_observability.py` 21 tests,
  `test_csp_report_only.py` 10 tests).

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

- **Status:** 2623 tests pass, 83 skipped (fast lane). The optional
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
  signing yet, no SBOM attestation.
- **Next:** cosign signing, SBOM via `syft`, SLSA provenance, GHCR publish.
- **Done in this pass:** image-build lane.

## Phased plan (from the deep-research report)

| Phase | Window | Theme | Items |
|-------|--------|-------|-------|
| Late Q2 | 2026-06 | Hygiene + hard gates | W1, W2, W3, W4, W5, W6, W6.5, W7, W7.5, W8, W9, W10, W11 (this pass) |
| Q3 | 2026-07 → 2026-09 | Observability dashboards + storage split v5 | Grafana, Prometheus alerts, raise Postgres coverage floors, v5 column drop |
| Q4 | 2026-10 → 2026-12 | DR + release engineering | W12, W13 |
| Q1 2027 | 2027-01 → 2027-03 | Storage split v6 + v2 dashboard auth | v6 JSONB, HTTP-only cookie auth |

## Out-of-scope

- Replacing the FastAPI surface with gRPC.
- Multi-region active/active.
- On-prem air-gapped install story.
