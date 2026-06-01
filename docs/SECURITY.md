# Security

**Last refreshed:** 2026-06-02
**Status:** Security controls exist, but public-production security is not validated

This document describes implemented controls and remaining risks. It is not a penetration-test report.

## Current Evidence

| Area | Evidence | Status |
| --- | --- | --- |
| API key auth | `backend/app/utils/rbac.py`, middleware in `backend/app/main.py` | Verified |
| RBAC route matrix | Freshly regenerated with `scripts/route_auth_matrix.py --format markdown`; archived combined route/security/CORS evidence remains in prior refresh docs | Verified for route registration evidence |
| Production secret validation | `scripts/check_prod_env.py --env-file .env.production.example` failed intentionally on placeholders; older combined route/security/CORS evidence remains archived | Verified for placeholder rejection |
| URL safety/SSRF checks | `backend/app/url_safety.py` rejects non-http(s), loopback/private IPs, metadata hosts, and internal names | Verified by code/tests |
| Rate limiting | `backend/app/rate_limiter.py` | Verified, single-process only |
| Public LLM fallback control | `DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS=false` by default; tests verify disabled Pollinations/g4f fallbacks do not make unauthenticated external calls | Verified |
| Audit logging | Audit logging modules and tests exist; production Compose sets `DATAFORGE_AUDIT_LOG_DIR=/app/backend/data/logs` so read-only root does not break writes | Partially verified |
| CORS config | Central settings in `backend/app/config.py`; local Nginx preflight returned `200` for `https://yourdomain.com` and `400` for `https://evil.example` | Verified locally |
| CSP | `nginx.conf` includes security headers; `/app/` locally returned CSP, X-Frame-Options, nosniff, Referrer-Policy, and Permissions-Policy headers | Partially verified |
| Metrics protection | `/metrics` uses token protection when `DATAFORGE_METRICS_TOKEN` is configured; local Nginx returned 404 for public `/metrics`; Prometheus scraped internal `/metrics` with bearer token | Verified locally |
| Docs exposure | FastAPI docs routes disabled when `DATAFORGE_ENV=production`; local Nginx returned 404 for `/docs`, `/redoc`, and `/openapi.json` | Verified locally |

## Auth Mechanism

The backend accepts API credentials through `X-API-Key`, `Authorization: Bearer <token>`, and compatibility admin headers where configured. Roles are user, operator, and admin. In development with no configured keys, routes may be permissive; that mode must not be used as a production security model.

## Public Routes

Current route matrix classifies three public application routes: `/`, `/health`, and `/ready`. Static dashboard mounts exist separately at `/app` and `/dashboard`; treat them as internal surfaces.

## Metrics

`/metrics` is protected only when `DATAFORGE_METRICS_TOKEN` is configured. Local Compose verified public Nginx blocks `/metrics` with 404 while Prometheus scrapes `http://dataforge:8000/metrics` internally using the configured bearer token. This still needs validation in the target network.

## SSRF Boundary

URL safety checks reject unsupported schemes and common private/internal targets. DNS-based checks are stricter in production/staging than local smoke mode. These controls reduce SSRF risk but do not replace network egress controls.

## Remaining Security Risks

- No production penetration test has been run.
- Target-environment Nginx/docs/metrics exposure was not tested.
- Dashboard session/security model is internal-only.
- Rate limiting is in-memory and does not coordinate across multiple workers.
- CORS/CSP must be verified against the real production origin.
- Browser extraction can touch untrusted pages; sandbox, egress, timeout, and resource limits need deployment validation.
- Secrets are validated for placeholders/shape, but operators must generate and protect real secrets.
- Enabling public LLM fallbacks can send prompts to third-party services and should remain disabled unless explicitly reviewed.

## Before Public Deployment

1. Run route-auth tests and generate the matrix from the deployed build.
2. Run `scripts/check_prod_env.py` against the real uncommitted `.env`.
3. Re-verify `/docs`, `/redoc`, `/openapi.json`, and `/metrics` through the target ingress.
4. Verify CORS/CSP in a browser against the production domain.
5. Add network egress controls for browser workers.
6. Run a security review focused on SSRF, auth bypass, stored output exposure, dashboard risks, and export handling.
