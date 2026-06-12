# Auth And Tenant Boundary

Current truth source: `docs/AGENT_TRUTH.md`.

This document records the current authentication and tenant isolation boundary for future agents. It is based on code inspection and the generated route auth matrix.

## Central Auth Context

Authentication is centralized in `backend/app/utils/rbac.py`.

`AuthContext` currently includes:

- `role`
- `user_id`
- `source`
- `org_id`
- `project_id`

Supported sources observed in code:

- env-backed or persistent API key
- bearer token through the same API-key path
- signed session cookie
- explicit dev bypass only when enabled in development/test settings

Future agents must not add ad hoc auth checks in routers. Use:

- `resolve_auth_context(request, allow_cookie=True)`
- `require_principal([...])` for tenant-scoped resources
- `require_role([...])` for role-only system resources
- `can_access_scoped_resource(...)` for owner/org/project checks

## Tenant-Scoped Resource Policy

Minimum current policy:

- Admin role has all-access.
- Env-backed operator keys may act as all-access operator keys when no `org_id` is present.
- Persistent/project-scoped operator keys remain scoped to their org/project.
- User role accesses own `created_by` resources or resources in the authenticated org/project where implemented.

Tenant-scoped resources must check before returning or mutating:

- jobs
- results
- job events
- exports
- recycle-bin items
- workflows
- auth profiles
- scheduled monitoring jobs
- audit logs and billing records when exposed

## Current Route Matrix Status

Generated artifacts:

- `docs/ROUTE_AUTH_MATRIX.md`
- `artifacts/audit/ROUTE_AUTH_MATRIX.json`

Prompt 5 matrix result:

- API route rows: 114
- Unknown auth rows: 0
- Unknown tenant-scope rows: 1
- Unknown tenant-scope route: `GET /api/saas/plan`

`/api/saas/plan` is tracked as `CAND-P1-ROUTE-TENANT-001`.

## Frontend Auth Boundary

`frontend/js/api.js` currently prefers HTTP-only session cookies and keeps fallback API/admin keys in JavaScript memory only. It does not persist API keys to `localStorage` or `sessionStorage` by design. The no-storage invariant is covered by `backend/tests/test_frontend_no_web_storage_for_keys.py` and frontend API tests.

Missing current proof: browser E2E for login/logout/session expiry and protected-route denial. This is already tracked as `CAND-P1-FRONTEND-AUTH-001`.

## Rules For Future Work

- New tenant resources must persist `created_by`, `org_id`, and `project_id` at creation.
- List endpoints must filter by `AuthContext`.
- Get/update/delete/export/run endpoints must check owner/org/project before returning data or side effects.
- Denied cross-tenant access should return 404 or 403 according to existing route policy and should be audit logged where audit logging exists.
- Public API exemptions must remain explicit and documented in the route auth matrix.
