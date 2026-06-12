# DataForge Scraper — Security Model

Date: 2026-06-13
Commit: `7d47045`

This document describes the security architecture for the current checkout. For threat models, see `artifacts/audit/AUTH_PROFILE_THREAT_MODEL.md`. For safety/acceptable-use policy, see `docs/SAFETY_AND_ACCEPTABLE_USE.md`.

---

## 1. Authentication

### API Keys (project-scoped)
- Format: `dfk_<43 base64url chars>` (256-bit entropy)
- Stored as SHA-256 hash; raw key never persisted
- Constant-time comparison via `hmac.compare_digest`
- Scopes: `read`, `write`, `admin`
- Revocable (soft-delete via `revoked_at`)

### Session Cookies
- Server-side signed sessions
- `httpOnly`, `SameSite=Lax`, `Secure` in production
- Session secret from `DATAFORGE_SESSION_SECRET` env var
- Fails closed in production if secret is empty

### Operator/Admin Keys
- Configured via `DATAFORGE_API_KEY`, `DATAFORGE_OPERATOR_API_KEY`, `DATAFORGE_ADMIN_API_KEY`
- Constant-time comparison against configured keys
- Development bypass (`ALLOW_INSECURE_DEV_AUTH`) disabled in production

### Bearer Tokens
- Bearer auth resolved through `resolve_auth_context()`
- Supports API keys in Bearer header format

---

## 2. Authorization (RBAC)

Centralized through `app.utils.rbac`:

- `resolve_auth_context(request)` — resolves role + identity from request
- `require_principal(roles)` — enforces role + populates org/project context
- `require_role(roles)` — enforces role only
- `require_role_with_user(roles)` — enforces role + returns user_id
- `can_access_scoped_resource()` — tenant isolation check

### Roles

| Role | Source | Access |
|------|--------|--------|
| `ADMIN` | `DATAFORGE_ADMIN_API_KEY` | All-access |
| `OPERATOR` | `DATAFORGE_OPERATOR_API_KEY` or project API key | Org/project-scoped or all-access |
| `USER` | Session cookie or API key | Own resources only |

---

## 3. Tenant Isolation

Every resource carries owner fields (`user_id`/`created_by`, `org_id`, `project_id`). Access is checked via `can_access_scoped_resource()`:

- Owner match: ✅
- Same org match: ✅
- Admin: ✅ (all-access)
- Operator: depends on policy (all-access for env-backed keys, org-scoped for project keys)
- Cross-tenant: ❌ (403/404)

Covered resources: jobs, results, events, exports, recycle bin, workflows, auth profiles, scheduled monitoring, audit logs.

---

## 4. URL Safety

- Rejects: non-HTTP schemes, private/internal IPs, metadata endpoints, internal TLDs, disallowed ports
- Admin domain denylist consulted before any fetch
- Crawl policy: per-domain concurrency, delays, retries, cooldowns
- Session URL detection: identifies temporary/session-bound parameters

---

## 5. Data Protection

### At Rest
- API keys: SHA-256 hashed
- Passwords: PBKDF2-HMAC-SHA256 (600,000 iterations, per-user salt)
- Auth profile storage state: field exists but encryption not yet implemented

### In Transit
- TLS required for production (not yet proven in staging)
- API responses strip sensitive fields (`encrypted_storage_state`, `password_hash`, `key_hash`)

### In Logs
- Validation scripts redact common secret patterns
- Audit logger never writes raw keys, tokens, or passwords
- `_safe_profile()` strips `encrypted_storage_state` from API responses

---

## 6. Rate Limiting

- Global rate limiter middleware on all `/api/*` routes
- Configurable via env vars
- Rate limit stats endpoint with Prometheus hit counters

---

## 7. Audit Logging

See `docs/AUDIT_LOGS.md`. Covers: auth events, RBAC decisions, admin actions, data access, job lifecycle, system events.

---

## 8. Dependency Security

- Bandit: 0 issues (58,634 LOC scanned)
- pip-audit: 60 vulnerability records in 21 packages (needs clean venv triage)
- See `docs/CI_STATUS.md` and `artifacts/audit/SECURITY_REVIEW_BASELINE.md`

---

## 9. Frontend Security

- CSP headers configured in middleware
- No raw tokens/cookies in frontend state
- API key management: raw key shown once, never stored in browser

---

## 10. Remaining Security Risks

| Risk | Severity | Status |
|------|----------|--------|
| Auth profile encryption not implemented | High | Open |
| pip-audit: 60 vulnerability records | Medium | Needs triage |
| No email verification on signup | Medium | Open |
| No password reset flow | Medium | Open |
| Staging TLS not proven | High | Open |
| Backup encryption not implemented | Medium | Open |
| No penetration test | Medium | Open |
