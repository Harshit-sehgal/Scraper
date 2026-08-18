# DataForge Scraper — API Changelog

All notable changes to the DataForge Scraper API are documented here.

## 0.1.0 (2026-06-29)

### Added

#### Core Extraction
- Initial job creation `POST /api/jobs` with manual and scheduled modes
- Job lifecycle: `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}`
- Paginated job results `GET /api/jobs/{id}/results` with cursor-based navigation
- Job events log `GET /api/jobs/{id}/events` with level filtering
- Extraction preview `POST /api/scraper/preview` for dry-run extraction
- Debug endpoint `GET /api/jobs/{id}/debug` with per-domain crawl state
- Recycle bin: `GET /api/recycle_bin`, `POST /api/recycle_bin/{id}/restore`, `DELETE /api/recycle_bin/{id}`, `DELETE /api/recycle_bin`

#### Fetch Strategies
- `httpx_smart` — Fast HTTP-only extraction
- `playwright_full` — Full browser rendering with JavaScript
- `hybrid` — Cascade from HTTPX to Playwright when needed

#### Anti-Bot & Safety
- Anti-bot engine with browser fingerprint randomization
- Proxy provider integration (HTTP, HTTPS, SOCKS5)
- SSRF protection with URL safety validation
- CSP report-only middleware
- Security headers (HSTS, X-Frame-Options, X-Content-Type-Options)

#### Authentication & Authorization
- API key authentication (Bearer token, X-API-Key header)
- Session-based cookie auth
- RBAC with Admin, Operator, and User roles
- SaaS org/project isolation
- Acceptable Use Policy (AUP) enforcement

#### Billing & Usage
- Usage tracking `GET /api/saas/usage`
- Plan enforcement with configurable limits
- Billing checkout/webhooks (PayPal)
- Subscription tier management

#### Monitoring & Observability
- Prometheus metrics at `/metrics`
- Structured JSON access logging
- Request ID propagation (`X-Request-ID`)
- Rate limiting with per-IP and global counters
- Health checks at `/health` and `/ready`

#### Developer Experience
- Python SDK (`from sdk import DataForge`)
- OpenAPI 3.1 spec at `/openapi.json`
- Swagger UI at `/docs`
- ReDoc at `/redoc`
- Route inventory and auth matrix generators
- 5 tutorial guides in `docs/tutorials/`

#### Data Quality
- Field-level type validation
- Record quality scoring
- Post-extraction processing pipeline
- Schema drift detection

#### Compliance
- GDPR right to erasure `POST /api/compliance/gdpr/forget`
- Data retention policies
- Audit logging for all extraction jobs

#### Infrastructure
- Docker Compose for development and production
- CI/CD pipeline (`.github/workflows/ci.yml`)
- Prometheus + Grafana monitoring stack
- Alertmanager alert delivery
- Nginx reverse proxy with TLS
- Postgres migration support

### Changed

- Initial release — no prior versions

### Fixed

- Initial release — no prior fixes

### Deprecated

- Nothing deprecated in this release

### Removed

- Nothing removed in this release

### Security

- API key enforcement on all `/api/*` routes (except documented public endpoints)
- CORS locked to configured origins in production
- Session secrets required in production
- Insecure dev auth forbidden in production
- Operator cross-tenant access gated behind explicit flag
- Rate limiting prevents DoS at both global and per-IP level
- CSP headers prevent XSS
- HSTS enabled in production
