# DataForge Scraper — SaaS Model

Date: 2026-06-13 (refreshed 2026-08-18 per `docs/EXECUTION_PLAN.md` E0.2)
Commit: `7d47045`

This document describes the SaaS identity and multi-tenancy model implemented in the current checkout. For the implementation source, see `backend/app/saas/`. Billing specifics live in `backend/app/billing/`; the money-loop plan lives in `docs/EXECUTION_PLAN.md` Phase 2.

---

## 1. Core Concepts

| Concept | Model | Storage | Description |
|---------|-------|---------|-------------|
| User | `saas.models.User` | `users` table | A human or service principal with email + PBKDF2 password hash |
| Organization | `saas.models.Organization` | `organizations` table | A tenant workspace; owns projects and memberships |
| Membership | `saas.models.Membership` | `memberships` table | Links a user to an org with a role (owner/admin/member/viewer) |
| Project | `saas.models.Project` | `projects` table | A grouping within an org for jobs, workflows, API keys |
| API Key | `saas.models.ApiKey` | `api_keys` table | A project-scoped key with SHA-256 hash (raw key never stored) |

---

## 2. User Signup Flow

```
POST /api/saas/signup  →  SignupService.signup()
  ├─ Validates email uniqueness
  ├─ Hashes password with PBKDF2-HMAC-SHA256 (600,000 iterations)
  ├─ Creates User record
  ├─ Creates default Organization ("{user}'s workspace")
  ├─ Creates default Project ("default")
  ├─ Creates OWNER Membership for user in org
  └─ Returns { user_id, email, organization_id, project_id }
```

The signup endpoint is explicitly public (no auth required). After signup, the user must accept the AUP via `POST /api/saas/aup/accept`.

---

## 3. Organization / Workspace Model

- Each user can belong to multiple organizations.
- Each organization has members with roles: `owner`, `admin`, `member`, `viewer`.
- The creator of an org automatically becomes `owner`.
- Memberships are soft-deleted via `removed_at` (not hard-deleted).
- Cannot remove the last owner from an org.

### Role Permissions

| Action | Owner | Admin | Member | Viewer |
|--------|-------|-------|--------|--------|
| View org details | ✅ | ✅ | ✅ | ✅ |
| List org members | ✅ | ✅ | ✅ | ✅ |
| Create projects | ✅ | ✅ | ❌ | ❌ |
| Invite/remove members | ✅ | ✅ | ❌ | ❌ |
| Manage API keys | ✅ | ✅ | ❌ | ❌ |
| Delete org | ✅ | ❌ | ❌ | ❌ |

Future: `billing_admin` role for plan/billing management.

---

## 4. Project Model

- Projects belong to a single organization.
- Jobs, workflows, auth profiles, and exports are project-scoped (via `org_id` + `project_id` fields).
- Users can only access projects in orgs they are members of.
- API keys are issued per-project with scope: `read`, `write`, `admin`.

---

## 5. API Key Model

- Raw key format: `dfk_<43 base64url chars>` (32 bytes entropy + `dfk_` prefix)
- Raw key is shown exactly once at creation and never stored.
- Stored record contains only `key_hash` (SHA-256 hex digest) and `key_prefix` (first 8 chars for dashboard display).
- Authentication compares request key against stored hash using constant-time comparison.
- Keys have scope: `read` (list/get only), `write` (create jobs), `admin` (manage resources).
- Keys can be revoked (soft-delete via `revoked_at`).
- `last_used_at` is bumped on successful auth (best-effort, non-blocking).

---

## 6. Tenant Isolation

Every resource that can hold tenant data carries owner fields:

| Resource | Owner Fields |
|----------|-------------|
| Jobs | `created_by`, `org_id`, `project_id` |
| Workflows | `user_id`, `org_id`, `project_id` |
| Auth Profiles | `user_id`, `org_id`, `project_id` |
| Scheduled Jobs | `user_id`, `org_id`, `project_id` |
| Exports | Accessed via job ownership |
| API Keys | `project_id` |

Access checks use the centralized `can_access_scoped_resource()` helper in `app.utils.rbac`, which enforces:
- Owner match: user can access own resources
- Org match: user can access same-org resources
- Admin/operator: all-access (opt-in, tested)
- Cross-tenant access: denied (403/404)

---

## 7. Acceptable Use Policy (AUP)

- Current AUP version: `2026-06-11-v1`
- Users must accept the AUP before performing protected actions (enforcement point: future).
- AUP acceptance is tracked with `aup_accepted_at` and `aup_version_accepted`.
- Re-accepting the same version is idempotent (keeps first timestamp).
- Accepting a new version updates both timestamp and version.

---

## 8. Storage

- Identity store uses a separate SQLite database (`identity.db` by default) to avoid coupling with the legacy job store schema.
- WAL journal mode for concurrent read safety.
- Thread-safe via per-instance `RLock`.
- Abstract `IdentityStore` contract allows swapping to Postgres later.
- Health check returns user/org/key counts.

---

## 9. What Is Built vs What Is Still Unproven

Correction 2026-08-18 (E0.2): this section previously listed PayPal
integration and plan enforcement as "not yet implemented". That is
stale. The current checkout contains:

- **Billing module**: `backend/app/billing/` — `checkout.py`, `webhooks.py`,
  `service.py`, `models.py` (PayPal migration flow).
- **Quota/plan enforcement**: `_enforce_api_auth_and_quota` in
  `backend/app/middlewares.py` plus `backend/app/plan_enforcer.py`
  (`_PLAN_LIMITS`), wired into job creation and export paths.
- **Durable metering**: `backend/app/utils/usage_ledger.py` persists
  quota + events to SQLite; persistence fixed 2026-08-18 (Session 97 —
  quotas previously vanished on restart).

**Still unproven (not implemented or not end-to-end verified):**

- PayPal sandbox end-to-end: signup → checkout → webhook → entitlement
  flip → limit → upgrade → resume. This is `docs/EXECUTION_PLAN.md`
  task E2.3.
- Plan hard-stop (403 on job creation at tier limit) verified
  end-to-end against a deployed environment (E2.1).
- Usage metering confirmed against the PRD §4 pricing metric (page
  fetches/month) with no double counting (E2.2).
- Email verification on signup (partial frontend exists; flow not
  proven end-to-end).
- Password reset flow.
- Postgres parity for the identity store.
- Frontend account/workspace management pages.
- AUP enforcement at protected-action time (acceptance tracking exists;
  enforcement point remains future).
