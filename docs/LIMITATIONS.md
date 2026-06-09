# Limitations

**Last refreshed:** 2026-06-08

DataForge Scraper is a configurable extraction platform, not an all-powerful scraper.

## Product Limits

- It works only on accessible websites where scraping is allowed and technically feasible.
- It cannot guarantee extraction from every site or every page structure.
- It cannot guarantee bypass of anti-bot systems.
- It cannot guarantee extraction accuracy without benchmark datasets and thresholds.
- It is a pre-production candidate, not a validated public production service.

## Validation Limits

- Safe SQLite tests: `3025 passed, 78 skipped, 0 failed` (100% clean pass — see PROJECT_STATUS.md).
- Postgres tests passed in prior sessions under `--run-postgres` (rate-limiter collisions resolved).
- Browser e2e tests were freshly validated passing: `10 passed, 0 failed in 10.11s` under `--run-browser`.
- Benchmark pytest package has smoke/config tests: `1 passed, 2 skipped`.
- Golden dataset live validation was freshly validated: `7 passed, 1 skipped in 42.74s` under `--run-golden-dataset` (gracefully skips transient external `httpbin.org` 503 error, highlighting target site dependency).
- Docker image build and a local production-like Compose smoke are documented historically.
- Target production deployment, TLS, load, backups, alert delivery, and disaster recovery were not validated.

## Security Limits

- Route auth is tested, but that is not a penetration test.
- Metrics protection depends on `DATAFORGE_METRICS_TOKEN` and correct production routing; local Compose verified Nginx blocks public `/metrics` and Prometheus scrapes internally.
- Rate limiting supports in-memory single-process mode by default, and shared database-backed multi-process mode when configured.
- Dashboard is internal-only until browser/session risks are addressed.
- URL safety checks reduce SSRF risk but do not replace production network controls.

## Ethical And Legal Boundary

Use this project only on websites where scraping is allowed or authorized. Respect robots.txt, terms of service, rate limits, access controls, and applicable law. Do not use it to scrape private, sensitive, or restricted data without permission. Anti-bot detection exists to identify blocked pages gracefully, not to circumvent website protections.

## Banned Claims

Do not claim production-ready, enterprise-grade, universal scraper, works on every website, anti-bot immune, fully autonomous, fully self-healing, guaranteed extraction, 100% accurate, complete, or fully benchmarked.
