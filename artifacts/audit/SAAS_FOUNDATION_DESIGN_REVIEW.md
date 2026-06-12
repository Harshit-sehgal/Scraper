# DataForge Scraper — SaaS Foundation Design Review

Date: 2026-06-13
Commit: `7d47045`
Scope: Planning and design review for Prompt 12 SaaS foundation. No implementation changes.

---

## 1. What Exists

### Identity Store (`backend/app/saas/identity_store.py`)

Complete SQLite-backed identity store with abstract `IdentityStore` contract and concrete `SQLiteIdentityStore` implementation. Uses WAL journal mode, foreign keys, and thread-safe locking.

**Tables:**
- `users` — id, email (UNIQUE), display_name, status, password_hash, created_at, email_verified_at, aup_accepted_at, aup_version_accepted
- `organizations` — id, name, created_by_user_id, created_at
- `memberships` — id, user_id, org_id, role, created_at, removed_at (UNIQUE user_id+org_id)
- `projects` — id, org_id, name, created_by_user_id, created_at
- `api_keys` — id, project_id, user_id, name, key_hash (UNIQUE), key_prefix, scope, created_at, last_used_at, revoked_at

**Operations:** Full CRUD on all entities. Membership soft-delete via `removed_at`. API key lookup by hash. Org membership checks. Health check endpoint.

### Service Layer (`backend/app/saas/service.py`)

- **`SignupService.signup()`** — Creates user + default org + default project + owner membership in one transaction. Password hashed with PBKDF2-HMAC-SHA256 (600,000 iterations).
- **`ApiKeyService`** — `issue()` generates raw key shown once, stores only SHA-256 hash. `authenticate()` looks up by hash with constant-time comparison. `revoke()` soft-deletes. `list_for_project()` returns keys.
- **`MembershipService`** — `add_member()`, `remove_member()`, `list_active_members()`, `is_active_member()`.
- **Password hashing** — `hash_password()` / `verify_password()` with per-user random salt and `hmac.compare_digest`.
- **API key generation** — `dfk_` prefix, 32 bytes entropy, SHA-256 hashing.

### SaaS Router (`backend/app/saas/router.py`)

**Endpoints:**
- `POST /api/saas/signup` — self-service signup (public, 201)
- `POST /api/saas/aup/accept` — record AUP acceptance
- `GET /api/saas/aup/status` — check AUP acceptance state
- `GET /api/saas/me` — get current user profile
- `POST /api/saas/orgs` — create org (operator/admin)
- `GET /api/saas/orgs` — list user's orgs
- `GET /api/saas/orgs/{org_id}` — get org detail
- `POST /api/saas/projects` — create project in org (operator/admin)
- `GET /api/saas/orgs/{org_id}/projects` — list org's projects
- `GET /api/saas/projects/{project_id}` — get project detail
- `GET /api/saas/orgs/{org_id}/members` — list org members
- `DELETE /api/saas/memberships/{membership_id}` — remove member (operator/admin)
- `GET /api/saas/plan` — get current plan info (stub: free tier)

**Auth:** All org/project/member routes require `require_role_with_user`. Signup is explicitly public in middleware and route matrix.

### Usage Ledger (`backend/app/utils/usage_ledger.py`)

- `UsageLedger` class with `record_usage()` (atomic check-and-increment under lock) and `check_quota()`.
- Supports idempotency keys for deduplication.
- Tracks: api_request, job_created, page_fetched, browser_minute, export_created, workflow_run.
- Quota enforcement: blocks over-limit actions.

### Audit Logger (`backend/app/audit_logger.py`)

Comprehensive audit logging with typed events:
- `log_auth_event()` — auth attempts, failures, session events
- `log_rbac_event()` — role-based access decisions
- `log_admin_action()` — admin operations
- `log_data_access()` — data access patterns
- `log_job_event()` — job lifecycle events
- `log_system_event()` — system-level events

Each event includes: actor, action, target_type, target_id, org_id, project_id, domain (if applicable), timestamp, metadata (redacted).

### Models (`backend/app/saas/models.py`)

Complete Pydantic models: `User`, `UserStatus`, `Organization`, `Membership`, `MembershipRole`, `Project`, `ApiKey`, `ApiKeyScope`. All with field validation.

### Plan / Billing Stubs

- `PlanTier`: free, starter, pro, enterprise
- `GET /api/saas/plan` returns `PlanInfoResponse` with hardcoded free-tier defaults
- No real plan enforcement or payment integration yet

---

## 2. What Is Missing

### Payment Integration
- No Stripe/Paddle/other payment provider integration
- No subscription management
- No invoice generation
- No billing webhook handling

### Plan Enforcement
- Plan limits are returned by `/api/saas/plan` but not enforced by any middleware or route
- No per-plan quota caps (max_jobs, max_scrapes, max_teammates, max_projects)
- No plan upgrade/downgrade flow

### Project-Scoped API Key Routes
- API key CRUD exists in service layer but no public router endpoints
- Missing: `POST /api/saas/projects/{id}/keys`, `GET /api/saas/projects/{id}/keys`, `DELETE /api/saas/projects/{id}/keys/{key_id}`

### Retention / Deletion Endpoints
- Recycle bin exists for jobs but no organization-level data deletion
- No "delete my account" flow
- No "delete project data" flow
- No configurable retention windows

### Account Management
- No email verification flow
- No password reset flow
- No 2FA

### Team Invitations
- Membership management exists but no invitation flow (invite by email, accept/decline)
- `POST /api/saas/orgs/{org_id}/invite` would be needed

### Billing / Usage Dashboard
- No frontend usage page
- No frontend billing page
- No frontend plan management

---

## 3. Architecture Assessment

### Strengths
- Clean separation: models → store (abstract + SQLite) → service → router
- Password hashing is current (PBKDF2-SHA256, 600K iterations, OWASP 2023+)
- API keys hashed at rest, raw key never stored, constant-time comparison
- Tenant isolation enforced through org/project membership checks
- AUP acceptance tracked with versioning
- Identity store uses its own DB file to avoid coupling with job store schema

### Risks
- In-memory stores for auth profiles, workflows, and scheduled monitoring (not backed by identity store)
- No Postgres parity proven for identity store (SQLite-only in tests)
- Plan enforcement gap: `/api/saas/plan` returns limits but nobody checks them
- No rate limiting per org/project

### Recommended Next Steps
1. Add API key management router endpoints
2. Wire plan limits into route middleware for quota enforcement
3. Add project-scoped deletion endpoints
4. Add email verification flow (or defer with honest documentation)
5. Prove Postgres parity for identity store tables

---

## 4. Do-Not-Do Warnings

- Do not store raw API keys — hash is already in place, keep it
- Do not bypass membership checks for org/project access
- Do not expose password hashes or key hashes in API responses
- Do not implement payment without legal/compliance review
- Do not fake production billing — stub or test mode only until real integration
