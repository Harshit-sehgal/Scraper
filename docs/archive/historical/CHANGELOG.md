# Changelog — DataForge Scraper

All notable changes to the DataForge Scraper platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0-observability] — 2026-05-27

### Added
- **JWT & Key-Based RBAC**: Introduced standard Role-Based Access Control (RBAC) supporting `admin`, `operator`, and `user` privileges.
- **Route guards**: Added route guards guarding job creations, cancellations, and recycle bin purges under custom dependency resolvers.
- **OPERATOR_API_KEY**: Added dedicated operator settings configuration mapping to job actions, leaving read-only status checks to the general `API_KEY`.
- **Prometheus Alerting Rules**: Added `prometheus_alerts.yml` with critical alerts on Queue Backlog (> 100), high job failures, DB connection issues, and response latencies (> 2.0s).
- **Expanded Grafana Overview Dashboard**: Added metrics panels for P95 latency histograms, DB error rates, and failed jobs counters.
- **Postgres Queue schema version 3**: Added a `execution_time_ms` column to `queue_task_history` to track precise worker task runtimes in the background.

### Fixed
- **Pyflakes Lints**: Fixed minor unused imports in `rbac.py` and `test_rbac.py` to keep pyflakes checks at exactly zero warnings.
- **Production Tests Auth Integration**: Updated production lifecycle and enqueue failure cleanup test cases to supply authenticated `X-API-Key` headers under monkeypatched production modes.

---

## [1.0.0-hardened] — 2026-05-27

### Added
- **Unsafe `eval()` Removal**: Replaced all unsafe eval blocks in `topology_state.py` with `ast.literal_eval` coupled with strict 2-tuple validations.
- **SSRF Hardening**: Implemented IP validation block middleware preventing scrapers from reaching metadata endpoints or private subnet targets.
- **DNS-Independent Testing**: Mocked DNS lookups in testing suites so that production-hardening tests can run fully offline in secured SRE sandboxes.
- **Nginx Security Rules**: Added proxy location blocks routing `/metrics` internally while blocking public scraping with `404` return codes. Tightened `client_max_body_size` to `10m` globally.
- **CI Config Checkers**: Added automated YAML, JSON, `nginx -t`, and `promtool check config` validators in GHA workflow actions.
- **SRE Quick Check Script**: Implemented `scripts/sre_quick_check.sh` aggregating compilation, import boundaries, lint validations, and local unit test executions under a single command.
- **Dev Dependencies**: Declared `PyYAML` and `pyflakes` formally in `requirements-dev.txt`.
