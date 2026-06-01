# Architecture

**Last refreshed:** 2026-06-01
**Status:** Actual architecture map from code inspection and fresh validation

DataForge Scraper is organized as a FastAPI backend, Playwright/browser extraction layer, storage and queue abstractions, export utilities, telemetry/diagnostics, security helpers, a static dashboard, and a set of experimental adaptive modules.

## Layer Map

| Layer | Main files | Purpose | Maturity | Test coverage | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| API layer | `backend/app/main.py`, `backend/app/routers/*.py` | FastAPI app, middleware, health/readiness, job/export/scraper/operator routes | Core | Route auth tests, API tests in safe suite | Production exposure must be verified through Nginx | Keep |
| Job lifecycle | `backend/app/job_store.py`, `backend/app/services/*`, `backend/app/worker*.py` | Job persistence, state changes, queue dispatch | Core | Safe suite, Postgres optional suite, local Compose worker smoke | Multi-job/failure production behavior unvalidated | Keep and broaden deployment tests |
| Scraper/browser | `backend/app/scraper.py`, `backend/app/browser_pool.py`, `backend/app/browser_network_capture.py` | HTTP/browser fetch, Playwright orchestration, page loading | Core | Browser suite evidence exists in archived docs; not freshly rerun in this cleanup | Broad real-world extraction not proven | Keep, add benchmark corpus |
| Extraction | `backend/app/extraction_orchestrator.py`, `backend/app/extractors/*`, `backend/app/schema_*.py` | Schema, selector, network payload, text fallback extraction | Core | Unit/API/browser tests | Real-world accuracy not proven | Keep, add benchmarks |
| Cleaning/enrichment | `backend/app/data_cleaner.py`, `backend/app/enrichment.py`, validators | Normalize and validate extracted records | Stable supporting | Safe suite | Quality varies by site/schema | Keep |
| Storage | `backend/app/storage_interface.py`, `backend/app/postgres_repository.py`, `backend/app/job_store.py` | SQLite local storage and Postgres repository selection | Core | SQLite safe suite; Postgres `1885 passed, 28 skipped`; Compose smoke and basic dump/restore | Production migration/failover/backups unvalidated | Keep, add deployment tests |
| Export | `backend/app/routers/exports.py`, `backend/app/utils/export.py` | CSV/JSON/Excel result export | Core | Safe suite | Large export behavior unvalidated | Keep |
| Telemetry/diagnostics | `backend/app/telemetry.py`, `backend/app/metrics.py`, `backend/app/diagnostics.py`, router endpoints | Observability, diagnostics, Prometheus metrics | Stable supporting | Safe suite, route matrix, local Prometheus target check | Target-network exposure still needs validation | Keep, verify target deployment |
| Security/auth | `backend/app/utils/rbac.py`, `backend/app/url_safety.py`, `backend/app/rate_limiter.py`, `backend/app/utils/prod_security_validator.py` | API keys, roles, URL safety, rate limiting, env validation | Core supporting | Route-auth and prod-security tests pass | Not a penetration test; rate limit is in-memory | Keep, harden |
| Dashboard | `frontend/`, static mounts in `main.py` | Internal static dashboard | Partial | Backend/static route coverage only | Public session/security model unvalidated | Keep internal |
| Experimental/adaptive | semantic/topology/federation/gossip/replay/strategy/selector-memory modules | Research and adaptive extraction behavior | Experimental | Mixed unit coverage | Easy to overclaim as intelligence/self-healing | Keep isolated and label |
| Infrastructure | `Dockerfile`, `docker-compose*.yml`, `nginx.conf`, `prometheus*.yml`, `grafana/`, `scripts/` | Local/prod deployment, validation, monitoring config | Pre-production | Docker build and local Compose smoke pass | Target deployment, TLS, backups, load, alerts unvalidated | Keep, validate target environment |

## Verified Architecture Evidence

```text
python3 -m compileall -q backend scripts architecture_validator.py
# passed with no output

PYTHONPATH=backend python3 architecture_validator.py
# VALIDATION PASSED: Architecture is lawful.
```

## Entry Points

- API server: `backend/app/main.py`
- Worker entry: `scripts/start_worker.sh`, `scripts/run_worker.py`
- Production API entry: `scripts/start_server.sh`
- Production env validation: `scripts/check_prod_env.py`
- Release validation: `scripts/verify_release.sh`, `scripts/verify_all.sh`

## Current Risk Summary

- The architecture is coherent enough for pre-production engineering.
- Local Docker build and Compose smoke are validated; target production deployment is not validated.
- Experimental modules must stay out of public feature claims until measured.
- Benchmark and golden dataset evidence is useful regression evidence but not strong enough for broad accuracy claims.
