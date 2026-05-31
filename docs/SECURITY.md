# Security

## Current Protections

### Authentication & Authorization
- **API key middleware** protects `/api/*` when keys are configured (via `secrets.compare_digest`, timing-safe).
- **RBAC** supports user, operator, and admin roles with per-route enforcement.
- **Generated route matrix** is available in `docs/ROUTE_AUTH_MATRIX.md`.
- Input validation via Pydantic models on all API request bodies.

### Network Security
- **CORS** is restricted to configured origins (no wildcard).
- **CSP** is configured in nginx with strict `script-src 'self'`; browser behavior under production CSP was not retested in this pass.
- **X-Frame-Options: DENY** (clickjacking protection).
- **X-Content-Type-Options: nosniff**.
- Nginx is configured to block public `/metrics`, `/docs`, `/redoc`, and `/openapi.json`; production proxy behavior still needs deployment validation.

### SSRF Protection (Application Level)
- Blocks localhost/127.0.0.1 and private IP ranges.
- Blocks cloud metadata endpoints (AWS, GCP, Azure).
- Validates redirects (max 5 hops).

### Production Validation
- Production env validation rejects common placeholder secrets, generated placeholder patterns, and duplicate user/operator/admin API keys.
- Startup gate (`scripts/check_prod_env.py`) validates env vars and can test database connectivity when Postgres is reachable.
- Production `/ready` responses are minimal (no internal state exposure).

## Important Limitations

### Dashboard
- **API key stored in `localStorage`** — NOT suitable for shared browsers or public kiosks.
- Dashboard should be used on **private/internal networks only**.

### Rate Limiting
- **Single-process only** - not distributed across workers.
- For multi-instance deployments, use nginx or WAF-level rate limiting.

### SSRF

- **Application-level only** - must be paired with network-layer egress controls (firewall rules, proxy ACLs) in production.
- DNS rebinding attacks are not protected at application layer.

### Audit Logging

- Structured event logging exists for auth events, RBAC violations, admin actions, job lifecycle, and data access paths covered by code/tests.
- Logs are written to `logs/audit.log` with automatic rotation (10 MB per file, 5 backups).
- Integrated into `api_key_middleware`; see `app/audit_logger.py`.
- Security events can be reviewed via the `get_recent_events()` API.

### Session Management

- No session tokens; API keys are long-lived and never expire.
- No refresh/rotation mechanism for keys.

## Production Secret Rules

Do not deploy with values containing:

- `change-me`
- `changeme`
- `CHANGE_ME`
- `replace-me`
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

Also ensure the user, operator, and admin API keys are three distinct secrets. Reusing one key across roles collapses RBAC boundaries and now fails production validation.

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
| Authentication | Good locally | Timing-safe API key comparison |
| Authorization | Partially verified | RBAC exists; generated route matrix covers registered routes |
| Input Validation | Implemented | Pydantic models on API request bodies |
| Network Security | Partial | Nginx/CSP config exists; production proxy path not tested here |
| SSRF Protection | Partial | App-level only; needs network-layer backing |
| Audit Logging | Implemented | Logging code exists; route-by-route coverage still needs review |
| Session Management | Missing | No token expiry or rotation |

For detailed security assessment, see [archive/audit/DELIVERABLE_7_SECURITY_REPORT.md](archive/audit/DELIVERABLE_7_SECURITY_REPORT.md) (archived baseline snapshot).
