# Security

## Current Protections

- API key middleware protects `/api/*` when keys are configured.
- RBAC supports user, operator, and admin roles.
- Production env validation rejects common placeholder secrets.
- Request body size is limited.
- URL safety code checks public HTTP(S) targets and redirect hops.
- Production `/ready` responses are minimal.
- Nginx blocks public `/metrics`, `/docs`, `/redoc`, and `/openapi.json`.

## Important Limitations

- The dashboard stores the user API key in `localStorage`; use it as an internal/private interface.
- Direct backend `/metrics` is public unless `DATAFORGE_METRICS_TOKEN` is set or a proxy blocks it.
- SSRF prevention in application code should be backed by production network egress policy.
- Route-level authorization should be covered by an explicit test matrix.
- Rate limiting is not proven distributed.
- The production dashboard currently permits CDN scripts in CSP.

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

Run:

```bash
python3 scripts/check_prod_env.py --env-file .env
```

before starting the production stack.

## Scraper-Specific Risk

Because this system fetches user-supplied URLs, SSRF is a primary risk. Production deployments should block access to localhost, private networks, metadata endpoints, Docker-internal networks, non-HTTP schemes, and redirect chains into private IPs at both application and network layers.
