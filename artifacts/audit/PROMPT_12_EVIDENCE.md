# Prompt 12 — SaaS Foundation Evidence Report

**Date:** 2026-06-13
**Commit:** Current working tree

---

## Implementation Summary

### Existing Foundation (all in place before this prompt)

| Component | Status |
|-----------|--------|
| Identity store (SQLite, users/orgs/projects/memberships) | ✅ |
| Password hashing (PBKDF2-SHA256, 600K iterations) | ✅ |
| API key service (issue, authenticate, revoke, SHA-256 hash) | ✅ |
| Usage ledger (atomic check-and-increment, idempotency keys) | ✅ |
| Audit logger (typed events, actor/action/target/timestamp) | ✅ |
| SaaS router (signup, AUP, orgs, projects, members, plan) | ✅ |
| Tenant isolation (org/project membership checks) | ✅ |

### Added in This Prompt

| Component | Status |
|-----------|--------|
| Project-scoped API key routes | ✅ |
| POST `/api/saas/projects/{id}/keys` | ✅ |
| GET `/api/saas/projects/{id}/keys` | ✅ |
| DELETE `/api/saas/projects/{id}/keys/{key_id}` | ✅ |
| API key tests | ✅ `backend/tests/test_saas_api_keys.py` |

### API Key Behavior

- API keys are hashed at rest (SHA-256)
- Raw key shown **only once** at creation time
- Key prefix stored for identification
- Revocation is soft-delete (sets `revoked_at`)
- Cross-project access denied via org membership checks

### Usage & Billing

- Usage ledger exists with atomic check-and-increment
- Tracks: api_request, job_created, page_fetched, browser_minute, export_created, workflow_run
- Plan enforcement: stubbed (returns free tier defaults)
- Payment provider: not integrated (by design — stub only)

### Audit & Retention

- Audit logger exists with typed events
- Tracks: login/session, API key create/revoke, job events, admin actions
- Retention/deletion: recycle bin for jobs exists; org-level data deletion is planned

### Tests

- `backend/tests/test_saas_router.py` — SaaS router tests
- `backend/tests/test_saas_api_keys.py` — API key CRUD tests
- `backend/tests/test_p0_auth_tenant.py` — Cross-tenant isolation tests

---

## Remaining Gaps

| Gap | Reason | Next Step |
|-----|--------|-----------|
| Payment provider integration | Deliberately not implemented per spec | Future sprint with legal/compliance review |
| Plan enforcement middleware | Returns limits but no enforcement at routes | Add quota checks to job creation routes |
| Email verification flow | Out of scope for MVP | Document as known gap |
| Password reset flow | Out of scope for MVP | Document as known gap |
| "Delete my account" flow | Partial — recycle bin for jobs only | Add cascading delete endpoints |
| Configurable retention policies | Not implemented | Add retention settings |

---

## Safe to Proceed

**Yes** — SaaS foundation is code-complete with identity, API key management, usage tracking, and audit logging. Remaining gaps are payment integration (deliberately deferred), email/2FA flows (MVP scope), and plan enforcement middleware.
