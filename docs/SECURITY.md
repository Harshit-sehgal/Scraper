# Security

## Current Protections

### Authentication & Authorization
- **API key middleware** protects `/api/*` when keys are configured (via `secrets.compare_digest` — timing-safe).
- **RBAC** supports user, operator, and admin roles with per-route enforcement.
- Input validation via Pydantic models on all API request bodies.

### Network Security
- **CORS** is restricted to configured origins (no wildcard).
- **CSP** is enforced via nginx — strict `script-src 'self'` (all assets vendored locally).
- **X-Frame-Options: DENY** (clickjacking protection).
- **X-Content-Type-Options: nosniff**.
- Nginx blocks public `/metrics`, `/docs`, `/redoc`, and `/openapi.json`.

### SSRF Protection (Application Level)
- Blocks localhost/127.0.0.1 and private IP ranges.
- Blocks cloud metadata endpoints (AWS, GCP, Azure).
- Validates redirects (max 5 hops).

### Production Validation
- Production env validation rejects common placeholder secrets.
- Startup gate (`scripts/check_prod_env.py`) validates env vars, database connectivity.
- Production `/ready` responses are minimal (no internal state exposure).

## Important Limitations

### Dashboard
- **API key stored in `localStorage`** — NOT suitable for shared browsers or public kiosks.
- Dashboard should be used on **private/internal networks only**.

### Rate Limiting
- **Single-process only** — not distributed across workers.
- For multi-instance deployments, use nginx or WAF-level rate limiting.### SSRF

- **Application-level only** — must be paired with network-layer egress controls (firewall rules, proxy ACLs) in production.
- DNS rebinding attacks are not protected at application layer.

### Audit Logging

- ✅ Structured event logging for auth events (failures + non-GET successes), RBAC violations, admin actions, job lifecycle, and data access.
- Logs are written to `logs/audit.log` with automatic rotation (10 MB per file, 5 backups).
- Integrated into `api_key_middleware`; see `app/audit_logger.py`.
- Security events can be reviewed via the `get_recent_events()` API.

### Session Management

- ❌ No session tokens — API keys are long-lived and never expire.
- ❌ No refresh/rotation mechanism for keys.

## Production Secret Rules

Do not deploy with values containing:

- `change-me`
- `changeme`
- `secret`
- `password`
- `admin`
- `default`
- `example`
- `yourdomain.com`
- `test`

Run before starting the production stack:

```bash
python3 scripts/check_prod_env.py --env-file .env
```

This fails if any placeholder secrets are detected.

## Scraper-Specific Risk

Because this system fetches user-supplied URLs, **SSRF is a primary risk**. Production deployments should:

1. Block access to localhost, private networks, and metadata endpoints at the **application layer** (already implemented).
2. Block access at the **network layer** (firewall, egress ACLs, proxy rules).
3. Block non-HTTP(S) URL schemes.
4. Limit redirect chain length (implemented: max 5 hops).
5. Restrict container network access to only required external endpoints.

## Security Maturity Summary

| Component | Rating | Notes |
|-----------|--------|-------|
| Authentication | ✅ Good | Timing-safe API key comparison |
| Authorization | ✅ Good | RBAC with per-route enforcement |
| Input Validation | ✅ Good | Pydantic models on all endpoints |
| Network Security | ⚠️ Partial | CSP is strict `script-src 'self'`; rate limiting single-process |
| SSRF Protection | ⚠️ Partial | App-level only; needs network-layer backing |
| Audit Logging | ✅ Implemented | Auth failures + non-GET mutations logged to rotating file |
| Session Management | ❌ Missing | No token expiry or rotation |

For detailed security assessment, see [archive/audit/DELIVERABLE_7_SECURITY_REPORT.md](archive/audit/DELIVERABLE_7_SECURITY_REPORT.md) (archived baseline snapshot).

