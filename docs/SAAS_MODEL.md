# DataForge Scraper — SaaS Model

Date: 2026-06-13
Commit: `7d47045`

This document describes the SaaS identity and multi-tenancy model implemented in the current checkout. For the implementation source, see `backend/app/saas/`.

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

## 9. What Is Not Yet Implemented

- Payment provider integration (PayPal — Subscriptions API)
- Plan enforcement in middleware/routes
- Email verification on signup
- Password reset flow
- Team invitation by email
- Project deletion cascade
- Organization deletion cascade
- Postgres parity for identity store
- Frontend account/workspace management pages
