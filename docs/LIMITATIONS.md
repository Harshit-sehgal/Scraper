# Limitations

**Last refreshed:** 2026-06-02

DataForge Scraper is a configurable extraction platform, not an all-powerful scraper.

## Product Limits

- It works only on accessible websites where scraping is allowed and technically feasible.
- It cannot guarantee extraction from every site or every page structure.
- It cannot guarantee bypass of anti-bot systems.
- It cannot guarantee extraction accuracy without benchmark datasets and thresholds.
- It is a pre-production candidate, not a validated public production service.

## Validation Limits

- Safe SQLite tests pass locally: `1863 passed, 72 skipped in 119.97s`.
- Postgres tests were reported passing previously: `12 passed in 3.82s` under `--run-postgres` *(archived from prior refresh — not re-run in this session)*.
- Browser e2e tests were reported passing previously: `10 passed in 10.04s` under `--run-browser` *(archived)*.
- Benchmark pytest package has only one smoke/config test: `1 passed, 1 skipped in 0.26s`.
- Golden dataset live validation was reported passing previously: `8 passed in 45.05s` under `--run-golden-dataset`, with lowest F1 `0.650` *(archived)*.
- Docker image build and a local production-like Compose smoke are documented historically.
- Target production deployment, TLS, load, backups, alert delivery, and disaster recovery were not validated.

## Security Limits

- Route auth is tested, but that is not a penetration test.
- Metrics protection depends on `DATAFORGE_METRICS_TOKEN` and correct production routing; local Compose verified Nginx blocks public `/metrics` and Prometheus scrapes internally.
- Rate limiting supports in-memory single-process mode by default, and shared database-backed multi-process mode when configured.
- Dashboard is internal-only until browser/session risks are addressed.
- URL safety checks reduce SSRF risk but do not replace production network controls.

## Ethical And Legal Boundary

Use this project only on websites where scraping is allowed or authorized. Respect robots.txt, terms of service, rate limits, access controls, and applicable law. Do not use it to scrape private, sensitive, or restricted data without permission. Anti-bot detection should support responsible failure handling, not abusive bypassing.

## Banned Claims

Do not claim production-ready, enterprise-grade, universal scraper, works on every website, anti-bot immune, fully autonomous, fully self-healing, guaranteed extraction, 100% accurate, complete, or fully benchmarked.
