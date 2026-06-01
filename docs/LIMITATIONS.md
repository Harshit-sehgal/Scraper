# Limitations

**Last refreshed:** 2026-06-01

DataForge Scraper is a configurable extraction platform, not an all-powerful scraper.

## Product Limits

- It works only on accessible websites where scraping is allowed and technically feasible.
- It cannot guarantee extraction from every site or every page structure.
- It cannot guarantee bypass of anti-bot systems.
- It cannot guarantee extraction accuracy without benchmark datasets and thresholds.
- It is a pre-production candidate, not a validated public production service.

## Validation Limits

- Safe SQLite tests pass locally: `1841 passed, 72 skipped in 116.54s`.
- Postgres tests pass locally with Docker/testcontainers: `1885 passed, 28 skipped in 138.54s`.
- Browser/local-server tests pass locally: `1858 passed, 55 skipped in 125.64s`.
- Benchmark pytest package has only one smoke/config test: `1 passed in 0.25s`.
- Golden dataset live validation passes modest enforced thresholds: `8 passed in 53.97s`, with lowest F1 currently `0.650`.
- Docker image build and a local production-like Compose smoke pass with a temporary ignored `.env`.
- Target production deployment, TLS, load, backups, alert delivery, and disaster recovery were not validated.

## Security Limits

- Route auth is tested, but that is not a penetration test.
- Metrics protection depends on `DATAFORGE_METRICS_TOKEN` and correct production routing; local Compose verified Nginx blocks public `/metrics` and Prometheus scrapes internally.
- Rate limiting is in-memory and single-process.
- Dashboard is internal-only until browser/session risks are addressed.
- URL safety checks reduce SSRF risk but do not replace production network controls.

## Ethical And Legal Boundary

Use this project only on websites where scraping is allowed or authorized. Respect robots.txt, terms of service, rate limits, access controls, and applicable law. Do not use it to scrape private, sensitive, or restricted data without permission. Anti-bot detection should support responsible failure handling, not abusive bypassing.

## Banned Claims

Do not claim production-ready, enterprise-grade, universal scraper, works on every website, anti-bot immune, fully autonomous, fully self-healing, guaranteed extraction, 100% accurate, complete, or fully benchmarked.
