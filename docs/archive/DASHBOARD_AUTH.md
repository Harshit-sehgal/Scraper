# Dashboard Authentication — Current Posture and v2 Plan

The deep-research report flagged the dashboard as storing the API key
in `sessionStorage`. This document records the **current** posture
(memory-only) and the **future** (v2) auth flow.

## Current (this round)

* The API key lives in module-scope variables (`_apiKey`,
  `_dashboardApiKey`) in `frontend/js/api.js` and
  `frontend/dashboard/dashboard.js`.
* Page reload clears the key. The user re-enters it on the dashboard's
  auth prompt.
* `sessionStorage` and `localStorage` are forbidden for the
  `dataforge_api_key` namespace by
  `backend/tests/test_frontend_no_web_storage_for_keys.py`. The test
  is wired into the "Frontend Syntax Check" CI step via
  `scripts/frontend_syntax_check.py`.

This is **acceptable** for an internal-only operator dashboard. The
attack surface is XSS-on-the-same-origin (mitigated by the absence of
any third-party JS and the CSP recommendation below), and the blast
radius is limited to the internal subnet that can reach the API.

## v2 plan (HTTP-only cookie)

Goal: remove the manual API key entry step on the dashboard without
re-introducing Web Storage.

Steps:

1. **Login endpoint** — `POST /api/auth/login` accepts a username +
   password or an API key, validates against `Settings`, and issues
   a short-lived (15 min) signed JWT or session ID in an HTTP-only,
   `Secure`, `SameSite=Strict` cookie.
2. **Logout endpoint** — `POST /api/auth/logout` revokes the session
   and clears the cookie.
3. **Reverse-proxy friendly** — keep `X-API-Key` for programmatic
   clients; do not force browser concerns onto API consumers.
4. **Cookie-based session middleware** — extract the cookie on every
   request, look up the session, and authenticate. Falls back to
   `X-API-Key` for non-browser clients.

Migration:

1. Add the auth router.
2. Add a settings-driven flag `DATAFORGE_AUTH_V2` (default off) to
   gate the new flow.
3. The dashboard reads the cookie on load (no manual entry).
4. Operators using a custom X-API-Key header continue to work.
5. After one release cycle of stability, make the v2 path default
   and deprecate the in-memory key path.

## CSP recommendation (related)

The backend **attaches a report-only** CSP header to every response via
`app.middlewares.csp_report_only_middleware` and exposes
`POST /api/system/csp-violations` to receive browser reports. Operators
tail the metric `dataforge_csp_violations_total{directive=...}` (via
`/metrics`) and tighten the policy iteratively. Set
`DATAFORGE_CSP_REPORT_ONLY=false` in production once the dashboard
shows zero violations for at least one release cycle.

Current report-only policy:

```
Content-Security-Policy-Report-Only:
  default-src 'self';
  script-src 'self' 'unsafe-inline';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  font-src 'self' data:;
  connect-src 'self';
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
  report-uri /api/system/csp-violations
```

Tighten to non-inline scripts once the static JS is split into
named files (today the dashboard uses a single `dashboard.js`).
