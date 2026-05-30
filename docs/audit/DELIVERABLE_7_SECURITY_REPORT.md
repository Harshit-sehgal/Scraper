# Deliverable 7: Security and Production Readiness Report

**Date:** May 30, 2026
**Method:** Code inspection, route enumeration, config file review, env file audit.

---

## Auth / Role Issues

| Issue | Severity | Details |
|-------|----------|---------|
| All API keys identical | 🔴 Critical | User, operator, and admin keys all = `0dd9362f...` in `.env`. RBAC is non-functional. |
| No route-level access control | 🟠 High | Middleware checks for ANY valid key. No `@requires_role` enforcement on routes. |
| Dashboard stores key in localStorage | 🟠 High | XSS vulnerability — any script injection exposes the API key. |
| Key validation not tested | 🟡 Medium | No tests verify that operator routes reject user keys (since all keys are same). |

## Secret Validation

| Issue | Severity | Details |
|-------|----------|---------|
| No hard startup gate | 🟠 High | `check_prod_env.py` is optional. Production can start with placeholder secrets. |
| `.env` committed on disk (not git) | 🟠 High | Real GROQ_API_KEY, DB passwords, Grafana password exposed to anyone with filesystem access. |
| .env.production has placeholder origin | 🔵 Low | `DATAFORGE_CORS_ORIGINS` set to `["https://app.dataforge.ai"]` which may not match actual deployment. |

## CORS

| Check | Status |
|-------|--------|
| CORS middleware present | ✅ Yes |
| Configurable via env | ✅ Yes |
| Wildcard allowed in production? | ❌ No — origin must be explicit in production |
| Default safe? | ⚠️ Partial — depends on config |

## CSP (Content Security Policy)

| Check | Status |
|-------|--------|
| Nginx CSP header | ✅ Strict: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` |
| Dashboard CDN references | ⚠️ Vendored files exist. Some may reference CDN origins. |
| CSP blocks dashboard features? | ⚠️ Needs verification with actual browser render |
| CSP documented accurately? | ⚠️ SECURITY.md now accurate after fixes |

## Rate Limiting

| Check | Status |
|-------|--------|
| Rate limiter exists | ✅ Yes |
| Distributed? | ❌ No — in-memory only (per-process) |
| Single-worker safe? | ✅ Yes |
| Redis/Postgres backed? | ❌ No |
| Documented honestly? | ✅ Now documented as in-memory |

## URL Safety / SSRF

| Check | Status |
|-------|--------|
| Blocks localhost | ✅ Yes |
| Blocks private IPs | ✅ Yes |
| Blocks metadata endpoints | ✅ Yes |
| Blocks file:// URLs | ✅ Yes |
| Blocks FTP/scheme abuse | ✅ Yes |
| DNS rebinding protection | ❓ Unknown |
| IPv6 protection | ❓ Unknown |
| Redirect following safe? | ❓ Unknown |
| **Verified by tests?** | ⚠️ Partially — `test_url_safety.py` exists (16 tests) |

## Docker Hardening

| Check | Status |
|-------|--------|
| Non-root user | ❓ Not inspected |
| Correct working directory | ❓ Not inspected |
| Healthcheck defined | ❌ No (E13) |
| Lock file used | ⚠️ Docker uses `requirements.txt`, not lock file |
| Python version consistent | ⚠️ 3.12 in Docker, host Python 3.12 — matches |
| Playwright install | ✅ Present in Dockerfile |
| Production env vars injected | ✅ Via docker-compose.prod.yml |

## Nginx Issues

| Check | Status |
|-------|--------|
| Reverse proxy configured | ✅ Yes |
| CSP headers | ✅ Yes (strict) |
| Rate limiting | ✅ Yes (nginx level) |
| Metrics exposure | ✅ Prometheus metrics exposed |
| Static file serving | ✅ Dashboard files served |

## Metrics Exposure

| Check | Status |
|-------|--------|
| Prometheus endpoint | ✅ `/metrics` (not inspected if auth-protected) |
| Grafana dashboards | ✅ Configured |
| Metrics auth | ❓ Unknown |
| Stack trace leakage | ✅ Starlette catches unhandled errors |

## Health / Readiness Leakage

| Check | Status |
|-------|--------|
| `/health` leaks config? | ✅ Returns minimal JSON |
| `/ready` leaks internals? | ⚠️ May expose storage backend type and schema version |
| Error responses detailed? | ⚠️ Internal errors may expose traceback in debug mode |
| Production error detail minimal? | ✅ FastAPI in production mode returns minimal errors |

## Dependency Pinning

| Check | Status |
|-------|--------|
| `requirements.txt` | ✅ Exists |
| `requirements.lock.txt` | ✅ Exists (pinned versions) |
| Docker uses lock file? | ❌ No — uses `requirements.txt` |
| `requirements-dev.txt` | ✅ Exists |
| Python version pinned | ✅ Python 3.12 |

## CI Gaps

| Check | Status |
|-------|--------|
| CI workflow exists | ✅ `.github/workflows/ci.yml` |
| Tests run in CI | ⚠️ Needs verification |
| Postgres service in CI | ❓ Unknown |
| Lint checks in CI | ❓ Unknown |
| Type check in CI | ❓ Unknown |
| Benchmark CI | ❌ No evidence |

---

## Summary of Critical Security Issues

1. **All three API keys are identical** — RBAC is non-functional
2. **Real API keys and DB passwords on disk** in `.env` (though gitignored)
3. **No production startup gate** — optional script only
4. **Dashboard localStorage API key** — XSS vulnerability
5. **Route-level access control missing** — operator/admin roles not enforced

## Honest Security Claim

**The project has basic API key authentication, in-memory rate limiting, SSRF protection, and a strict CSP. However, RBAC is ineffective (all keys identical), there is no production secret validation gate, and route-level access control is not enforced. This is suitable for internal/development use. Public deployment requires significant security hardening.**
