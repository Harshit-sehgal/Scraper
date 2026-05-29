# Project Status

This file is the current source of truth for project claims. Historical maturity reports were moved to `docs/archive/` and should not be used as current evidence.

## Verified

- Python syntax: `python3 -m compileall -q .` completed successfully during the audit.
- Backend import: `PYTHONPATH=backend python3 -c "import app.main"` completed successfully.
- Lint sanity: `python3 -m pyflakes backend/app scripts architecture_validator.py` completed successfully.
- Architecture validator: `PYTHONPATH=backend python3 architecture_validator.py` passed.
- Type check baseline: `python3 -m mypy backend/app --ignore-missing-imports` reports success after cleanup, with mypy notes that untyped function bodies are not checked.
- Test collection: `PYTHONPATH=backend python3 -m pytest --collect-only -q -o addopts=` collected 1711 tests.
- Local pytest: `PYTHONPATH=backend python3 -m pytest -q -ra -o addopts=` reported 1657 passed and 54 skipped.
- Production env checker rejects placeholder production secrets in `.env.production.example`.
- Production server and worker entrypoints run env validation when `DATAFORGE_ENV=production`.

## Partially Verified

- Playwright/browser tests run locally when socket/browser permissions are available.
- SSRF controls and redirect-hop validation exist and are covered by tests, but they are not a complete substitute for production network egress controls.
- API role boundaries exist for user/operator/admin actions, but a full route-by-route authorization threat model is still needed.
- Metrics exist and are blocked by Nginx at `/metrics`; direct backend exposure still depends on `DATAFORGE_METRICS_TOKEN`.
- Dashboard endpoints match many backend routes, but the browser UI remains internal/private and stores the user API key in `localStorage`.

## Implemented but Not Fully Validated

- Postgres storage and queue code paths.
- Production Docker Compose, Nginx, Prometheus, and Grafana stack.
- Semantic topology, replay, strategy evolution, selector memory, and adaptive recovery components.
- Manual live benchmark scripts.
- Long-running/longevity validation scripts.
- Production CSP with third-party dashboard CDN scripts.
- Distributed behavior beyond single-process local tests.

## Known Failures

- `python` is not available in the audited shell; use `python3`.
- Full pytest cannot run inside the default sandbox because local HTTP/browser tests require socket binding.
- `.env.production.example` intentionally fails `scripts/check_prod_env.py` because it contains placeholders.
- Several manual benchmark files are not collected by pytest under the current `pytest.ini`.

## Production Blockers

- Production Docker Compose must be tested against a real environment with real secrets and domain-specific CORS.
- Postgres tests need a real service-container CI job or equivalent release gate.
- Docker builds currently use `backend/requirements.txt`, which uses version ranges rather than a strict lock file.
- Dashboard CDN dependencies require either vendoring or an intentionally relaxed CSP.
- Rate limiting is in-process unless fronted by Nginx or another shared limiter.
- Live/replay benchmark methodology is not strong enough to claim broad reliability.

## Security Notes

- API key middleware protects `/api/*` when keys are configured.
- RBAC dependencies distinguish user, operator, and admin keys on many sensitive routes.
- Public liveness/readiness endpoints are intentionally unauthenticated; production readiness responses are now minimal.
- Direct backend `/metrics` should use `DATAFORGE_METRICS_TOKEN` if exposed. Nginx production config returns 404 for public `/metrics`.
- The frontend stores the normal API key in `localStorage`; treat it as an internal/private dashboard.
- The project is a scraper, so SSRF and egress policy must be treated as production-critical.

## Benchmark Limitations

- `backend/tests/test_benchmark_suite.py` uses fixture-based checks and one simulated recovery metric.
- `backend/tests/benchmark_smoke_test.py`, `backend/tests/hostile_benchmarks.py`, `backend/tests/replay_benchmark.py`, and `backend/tests/longevity_run.py` are not collected by pytest.
- Live benchmark scripts depend on external websites and network behavior.
- Accuracy metrics were corrected to penalize extra records and extra schema fields, but benchmark coverage still needs record-level golden datasets.

## Current Test Status

- Collection: 1711 tests collected after cleanup edits.
- Verified full local run: 1657 passed and 54 skipped.
- Focused fixed tests: production hardening, session recovery, three-way acquisition, Playwright E2E, job API E2E, and accuracy tests passed locally after fixes.
- Postgres tests: present but not fully validated locally with a real Postgres service in this audit.

## What Can Be Claimed Honestly

- The project includes a FastAPI backend and Playwright-based extraction paths.
- Basic syntax, import, pyflakes, architecture validation, mypy baseline, and local pytest were verified during this cleanup.
- The project includes job APIs, result export, telemetry, dashboard files, storage abstractions, queue code, production deployment files, and benchmark tooling.
- Production deployment files are present but require environment-specific validation before release.
- The project is a pre-production web extraction platform with meaningful test coverage and known validation gaps.

## What Must Not Be Claimed Yet

- Production ready.
- Fully autonomous or fully self-healing.
- Works on any website.
- Perfect extraction accuracy.
- Complete anti-bot resilience.
- Enterprise-grade security.
- Fully validated Postgres production readiness.
- Real-time streaming dashboard unless WebSocket/SSE streaming is implemented and verified.
- Fully centralized config while direct environment reads remain in some modules.

## Next Validation Steps

1. Add a Postgres CI job with a service container and run marked Postgres tests.
2. Build and smoke-test the production Docker Compose stack with real non-placeholder secrets.
3. Vendor dashboard CDN assets or explicitly accept the relaxed CSP risk.
4. Add route-level authorization tests for every sensitive endpoint.
5. Replace simulated recovery benchmark claims with real fixture/replay/live recovery benchmarks.
6. Add golden-record benchmark datasets that punish missing fields, wrong values, extra fields, extra records, duplicates, and malformed output.
7. Decide whether Docker should install from a strict lock file and update CI accordingly.
