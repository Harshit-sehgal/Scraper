# DataForge Scraper — Compliance & Crawl Policy

This document defines the ethical and operational boundaries for the DataForge web scraping platform.

## Allowed Uses

- Extracting publicly available business listings, contact information, and directory data
- Monitoring publicly accessible websites for changes
- Aggregating public data for analysis, research, or lead generation
- Archiving publicly available web content

## Prohibited Uses

- **No login bypass:** Do not scrape content behind authentication or paywalls.
- **No CAPTCHA solving:** Do not use automated CAPTCHA solving services.
- **No personal data collection:** Do not intentionally scrape personally identifiable information (PII) without explicit permission.
- **No credential stuffing:** Do not use the platform for credential testing or account enumeration.
- **No denial of service:** Do not configure concurrency levels that overload target servers.
- **No illegal content:** Do not scrape illegal content or use the platform for unlawful purposes.

## Operational Governance

### robots.txt

- By default, `CRAWL_RESPECT_ROBOTS=True` (configurable).
- When enabled, the platform performs a best-effort check against `robots.txt` before fetching.

### Rate Limiting

- Per-domain concurrency is controlled by `CRAWL_PER_DOMAIN_CONCURRENCY` (default: 2).
- A configurable delay between requests is enforced via `CRAWL_DEFAULT_DELAY_SECONDS` (default: 1.0s).
- Domains that exceed failure thresholds enter cooldown (`CRAWL_COOLDOWN_SECONDS`, default: 60s).

### Domain Policies

- `CRAWL_MAX_PAGES_PER_DOMAIN` limits total pages scraped from a single domain per job (default: 50).
- `CRAWL_MAX_RETRIES_PER_DOMAIN` controls max consecutive failures before cooldown (default: 3).

## Enforcement

- The platform's `DomainRuntimePolicy` enforces per-domain concurrency and cooldown automatically.
- The `inflection_point_roadmap` and `scraper_dossier` documents the platform's evolution and failure modes.
- All crawl parameters are configurable via environment variables (see `config.py`).

## Disclaimer

This software is provided for legitimate data collection purposes. Users are responsible for ensuring their usage complies with applicable laws, website terms of service, and ethical guidelines.
