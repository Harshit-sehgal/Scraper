# HTTPS / TLS Deployment Verification

The deep-research report's **Medium-4** finding is that the project's
nginx config historically did not actually serve HTTPS by default
while emitting HSTS over plain HTTP (a no-op that gives a false sense
of security). This document records the **current** posture and the
runtime checks operators should run after deployment.

## Current posture (this round)

`nginx.conf` ships three labelled server blocks:

| Block | Listener | Status | Purpose |
|-------|----------|--------|---------|
| A     | 443      | active | Production HTTPS with HSTS, security headers, ACME-friendly front |
| B     | 80       | active | 301 → HTTPS for everything except `/.well-known/acme-challenge/` and the `/health` / `/ready` probes |
| C     | 80       | commented | HTTP-only fallback for environments that cannot obtain a cert (local docker-compose, behind a TLS-terminating proxy) |

HSTS is emitted **only** on the 443 listener. MDN documents that
browsers ignore HSTS delivered over plain HTTP, so emitting it on
port 80 is a no-op that misleads operators — we do not do that.

The `backend/tests/test_nginx_tls_posture.py` static test asserts:

* HSTS is inside the HTTPS server block, not the HTTP one.
* HTTP block has a 301 redirect to HTTPS (preserving the path and query).
* The dev HTTP-only block is commented out and clearly marked
  HSTS-disabled.

## Operator verification checklist

Run these checks against a deployed stack before declaring TLS
ready. They mirror the report's "Add deployment verification that
proves: valid cert present, /health and /ready work over HTTPS,
HSTS header present on HTTPS response, no mixed-content errors on
dashboard."

```bash
# 1. Cert is valid and trusted
echo | openssl s_client -connect api.example.com:443 -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -dates -subject -issuer

# 2. /health works over HTTPS
curl -fsS -o /dev/null -w "status=%{http_code}\n" https://api.example.com/health

# 3. /ready works over HTTPS
curl -fsS https://api.example.com/ready

# 4. HSTS header is present on HTTPS
curl -sI https://api.example.com/ | grep -i strict-transport-security

# 5. HSTS header is NOT present on plain HTTP
curl -sI http://api.example.com/ | grep -i strict-transport-security \
  || echo "✅ no HSTS on HTTP (correct)"

# 6. Plain HTTP redirects to HTTPS
curl -sI http://api.example.com/api/jobs | grep -i location

# 7. The dashboard HTML does not reference http:// assets
curl -fsS https://api.example.com/app/ | grep -E "http://[a-z]" \
  || echo "✅ no mixed-content references"

# 8. ACME http-01 challenge path still works over plain HTTP
curl -sI http://api.example.com/.well-known/acme-challenge/example
```

Expected results:

| # | Expected |
|---|----------|
| 1 | `notBefore` in the past, `notAfter` ≥ 30 days out, `issuer` is a trusted CA |
| 2 | `status=200` |
| 3 | 200 with `{"status": "ok"}` or `"ok\n"` |
| 4 | `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` |
| 5 | "no HSTS on HTTP (correct)" |
| 6 | `location: https://api.example.com/api/jobs` |
| 7 | "no mixed-content references" |
| 8 | 200 or 404 — never 301 |

## Pitfalls to watch for

* **Cloudflare or AWS ALB in front** — those proxies terminate TLS
  *before* nginx. Use server block C (the commented HTTP-only fallback)
  for environments behind a TLS-terminating proxy.
* **Self-signed certs** — never use them in production. Letsencrypt
  and the major cloud CAs are free.
* **HSTS preload** — submitting to the browser preload list is
  irreversible. Only enable `preload` if the team is committed to
  HTTPS for the lifetime of the domain.
* **Certificate renewal** — Let's Encrypt certificates should be renewed
  before expiry. Operators can use a cron job on the host, a certbot
  container (not included in docker-compose.prod.yml), or a managed
  certificate service from their cloud provider.

## What this document is not

* Not a substitute for the upstream nginx docs.
* Not a renewal policy — see `docs/INCIDENT_RUNBOOK.md` for the
  rotation procedure.
* Not a CSP review — see `docs/DASHBOARD_AUTH.md` for the
  Content-Security-Policy plan.
