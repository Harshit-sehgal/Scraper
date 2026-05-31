# Production Readiness Checklist

**Status:** Pre-production candidate
**Last updated:** 2026-05-31
**Classification:** Gate checklist — nothing here is verified until the command is run in the target environment.

This document lists the gates that must pass before this project can be described as production-ready. Each item is concrete, testable, and falls into one of three states:

- **Not started** — No work done
- **In progress** — Some implementation exists
- **Validated** — Passed in target environment

---

## 1. Secrets and Environment

| Gate | Status | Notes |
|------|--------|-------|
| Strong unique user/operator/admin API keys generated | Not started | Must be distinct values, generated outside source control |
| Strong database password | Not started | Must not be a placeholder or reused credential |
| Strong Grafana password | Not started | Must not be 'admin', 'password', 'grafana', or 'change-me' |
| `.env.production` created from `.env.production.example` | Not started | Must never be committed to source control |
| Production env validation passes | Not started | `python3 scripts/check_prod_env.py --env-file .env` must pass |
| No real secrets committed to git | Validated | `.gitignore` blocks `.env*` files; examples contain placeholders |
| SSL/TLS certificate provisioned and auto-renewal configured | Not started | Let's Encrypt, cert-manager, or equivalent; must test renewal |
| Secret rotation policy documented | Not started | How to rotate API keys, DB passwords, Grafana passwords without downtime |

## 2. Build and Deployment

| Gate | Status | Notes |
|------|--------|-------|
| Docker image builds successfully | Not started | `docker build -f Dockerfile .` must pass |
| Docker Compose production stack starts | Not started | `docker compose -f docker-compose.prod.yml up -d` must succeed |
| All services reachable after startup | Not started | Postgres, backend, worker, Nginx, Prometheus, Grafana |
| No port conflicts with host | Not started | Verify port mappings in compose files |
| Worker process starts and connects to queue | Not started | Worker must initialize and begin polling |

## 3. Application Health

| Gate | Status | Notes |
|------|--------|-------|
| `/health` returns 200 | Not started | Must return `{"status": "healthy"}` or similar |
| `/ready` returns 200 | Not started | Must pass database connectivity check |
| Liveness probe configured (container orchestration) | Not started | Separate from readiness; detects hung processes |
| Readiness probe configured (container orchestration) | Not started | Must check DB/queue connectivity before accepting traffic |
| Application connects to Postgres | Not started | Storage backend must report connected |
| Application connects to worker queue | Not started | Queue backend must report connected |
| API key authentication works | Validated | Timing-safe comparison; 134 route auth tests pass locally |
| Route-level authorization enforced | Validated | Documented in `docs/ROUTE_AUTH_MATRIX.md`; 81 routes |

## 4. Security

| Gate | Status | Notes |
|------|--------|-------|
| CORS origins locked to real domains | Not started | No wildcard in production |
| CSP headers enforced by Nginx | Validated | `default-src 'self'` configured; needs browser testing |
| `/metrics` accessible only to internal Prometheus | Not started | Nginx blocks public access; token protection available |
| `/docs` and `/redoc` blocked in production | Not started | Nginx config intended to block; needs test |
| `/openapi.json` blocked in production | Not started | Same as above |
| SSRF application-layer checks active | Validated | Blocks private IPs, metadata endpoints, max 5 redirects |
| SSRF network-layer egress controls in place | Not started | Firewall, proxy ACLs, or container network policy |
| Rate limiting active for API routes | Partially validated | In-memory only; not distributed across workers |
| API docs auto-generated routes disabled | Not started | Must verify `docs_url=None, redoc_url=None` in production |
| Dashboard not accessible from public network | Not started | Must be behind VPN or internal network only |

## 5. Database and Storage

| Gate | Status | Notes |
|------|--------|-------|
| Postgres migration/init runs successfully | Not started | `init.sql` must execute and create schema |
| Job CRUD works against Postgres | Validated | 1881 Postgres tests pass locally |
| Worker queue works against Postgres | Validated | Queue integration tests pass |
| Storage backend configured to Postgres | Not started | `DATAFORGE_STORAGE_BACKEND=postgres` in production |
| Backup/restore procedure documented | Not started | No backup documentation exists |
| Data persistence verified across restarts | Not started | Must test that data survives container restart |

## 6. Frontend / Dashboard

| Gate | Status | Notes |
|------|--------|-------|
| Dashboard loads without console errors | Not started | Requires browser test under production CSP |
| API key entry works against production backend | Not started | Must test with real production credentials |
| Dashboard polls endpoints without errors | Not started | Network requests must succeed through Nginx |
| Dashboard not accessible from public internet | Not started | Internal network or VPN only |
| `sessionStorage` API key behavior verified | Validated | API key uses sessionStorage (cleared on tab close) |

## 7. Monitoring and Observability

| Gate | Status | Notes |
|------|--------|-------|
| Prometheus scrapes `/metrics` successfully | Not started | Must verify prometheus.yml targets are correct |
| Grafana dashboards load and display data | Not started | Dashboards must be imported and datasource configured |
| Alert rules configured and tested | Not started | `prometheus_alerts.yml` exists; needs validation |
| Audit logs are being written | Validated | Audit logger integrated into middleware |
| Log rotation configured | Validated | 10 MB per file, 5 backups |

## 8. Extraction and Scraping

| Gate | Status | Notes |
|------|--------|-------|
| Playwright/Chromium installed in Docker image | Not started | Must verify in built image |
| Basic extraction job runs successfully | Not started | Smoke test against a known-stable target |
| Export (CSV/JSON/Excel) works from production | Not started | Must test export endpoints through Nginx |
| Golden dataset extraction accuracy measured | Not started | Observational tests exist; no hard F1 thresholds enforced |

## 9. Operational Procedures

| Gate | Status | Notes |
|------|--------|-------|
| Graceful shutdown documented | Not started | How to stop services without data loss |
| Restart procedure documented | Not started | How to bring services back up |
| Failure recovery tested | Not started | Simulated module exists; no production recovery test |
| Load testing completed | Not started | No load testing performed |
| Incident response documented | Not started | No operational runbook exists |
| Log aggregation configured | Not started | Centralized log collection (e.g., Loki, ELK, CloudWatch) |
| Domain/DNS configured | Not started | A/AAAA records, CNAME, CDN (if applicable) |
| Egress IP addresses documented | Not started | Static IP if required for allowlisting with target sites |

## 10. Validation Commands

Run these in the target production environment before declaring readiness:

```bash
# Syntax and architecture
python3 -m compileall -q backend scripts architecture_validator.py
python3 architecture_validator.py

# Collection (should be 0 errors)
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=

# Local test baseline (SQLite)
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests -o addopts=

# Production env validation (must pass with real secrets)
python3 scripts/check_prod_env.py --env-file .env

# Route auth matrix generation
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 scripts/route_auth_matrix.py --format markdown

# Postgres tests (requires running Postgres)
PYTHONPATH=backend DATAFORGE_DATABASE_URL=postgresql://user:pass@host:5432/db \
  DATAFORGE_STORAGE_BACKEND=postgres \
  python3 -m pytest -q backend/tests --run-postgres -o addopts=

# Browser E2E tests (requires Playwright + Chromium)
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests/test_playwright_browser_e2e.py \
  backend/tests/test_session_bound_e2e.py --run-browser -o addopts=
```

Until every gate in this checklist passes in the target deployment environment, the project status must remain:

**«Pre-production candidate.»**
