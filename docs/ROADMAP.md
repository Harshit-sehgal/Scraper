# Roadmap

## 1. Stop False Claims

- Keep stale reports archived.
- Require evidence for new claims.
- Keep `PROJECT_STATUS.md` current.

## 2. Fix Failing or Weak Tests

- Preserve security behavior when tests fail.
- Convert manual benchmark files into collected tests or CI-called scripts where appropriate.
- Add no-assertion and placeholder-test audits.

## 3. Security Blockers

- Add route-level auth matrix tests.
- Add stricter SSRF tests for IPv6, redirects, DNS rebinding-like cases, and encoded host bypasses.
- Decide dashboard token handling strategy.

## 4. Production Startup

- Keep production env validation as a hard gate.
- Add production compose smoke tests in CI.
- Validate browser installation in image.

## 5. Benchmark Methodology

- Expand golden-record fixtures.
- Separate metric simulation, fixture, replay, live, hostile, and longevity results.
- Add reproducible benchmark reports with command/date/environment.

## 6. Dependency Reproducibility

- Decide whether Docker should install from lock files.
- Add lock verification in CI.

## 7. Dashboard Production Compatibility

- Vendor Chart.js/Tailwind or document and accept the relaxed CSP.
- Add dashboard smoke test under Nginx CSP.

## 8. Postgres and Browser Validation

- Add Postgres service-container CI.
- Run marked Postgres tests by default in the Postgres job.
- Add Playwright browser CI coverage.

## 9. Final Release Checklist

- Real production `.env` passes validation.
- Docker image builds.
- Production compose stack starts.
- `/health` and `/ready` pass.
- Nginx blocks docs/metrics publicly.
- Prometheus scrapes internally.
- Grafana starts with non-default password.
- Postgres migrations/init pass.
- Pytest, mypy baseline, pyflakes, and architecture validator pass.
