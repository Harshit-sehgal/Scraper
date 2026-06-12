# DataForge Scraper — API Keys

Date: 2026-06-13
Commit: `7d47045`

Project-scoped API keys for programmatic access. Implementation: `backend/app/saas/service.py` (ApiKeyService), `backend/app/saas/models.py` (ApiKey model).

---

## 1. Key Format

```
dfk_<43 base64url characters>
```

- Prefix `dfk_` makes keys identifiable in logs and UI (non-secret).
- 32 bytes of cryptographic randomness (256 bits entropy).
- Total key length: 47 characters.

---

## 2. Key Lifecycle

### Creation
```
ApiKeyService.issue(project_id, user_id, name, scope=WRITE)
  → generates raw key
  → stores SHA-256 hash + key_prefix (first 8 chars)
  → returns raw key ONCE to caller
```

The raw key is never logged, never stored, and never returned again.

### Authentication
```
ApiKeyService.authenticate(raw_key)
  → SHA-256 hash the raw key
  → lookup by hash in api_keys table
  → check revoked_at is NULL
  → bump last_used_at (best-effort)
  → return ApiKey record or None
```

Comparison uses `hmac.compare_digest` for constant-time matching.

### Revocation
```
ApiKeyService.revoke(api_key_id)
  → sets revoked_at = now
  → subsequent authenticate() calls return None
```

Revoked keys are never deleted — they remain in the database for audit trail.

### Listing
```
ApiKeyService.list_for_project(project_id, include_revoked=False)
  → returns all active keys for a project
```

---

## 3. Key Scopes

| Scope | Permissions |
|-------|-------------|
| `read` | List/get jobs, results, workflows, exports |
| `write` | Create jobs, run workflows, create exports |
| `admin` | Manage project resources, issue/revoke keys |

Default scope for new keys: `write`.

---

## 4. Key Security Properties

- **Hashed at rest:** SHA-256 hex digest stored; raw key never persisted.
- **Prefix-only display:** First 8 chars (`dfk_xxxx`) shown in dashboards.
- **Constant-time verification:** `hmac.compare_digest` prevents timing attacks.
- **Project-scoped:** Each key is bound to a single project. Cross-project access denied.
- **Revocable:** Soft-delete via `revoked_at`; no key reuse after revocation.
- **No raw key in logs:** Key generation uses `secrets.token_urlsafe`; hash function is deterministic but one-way.

---

## 5. API Key Storage Schema

```sql
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'write',
    created_at TEXT NOT NULL DEFAULT '',
    last_used_at TEXT DEFAULT NULL,
    revoked_at TEXT DEFAULT NULL
);
```

---

## 6. Integration With Auth System

API keys are resolved in `app.utils.rbac.resolve_auth_context()`:

1. Extract `Authorization: Bearer <key>` from request headers.
2. Hash the key, look up in identity store.
3. If found and active, resolve to `UserRole.OPERATOR` (for `write`/`admin` scope) or `UserRole.USER` (for `read` scope).
4. Populate `org_id` and `project_id` from the key's project → org chain.

---

## 7. Future: API Key Router Endpoints

Currently the `ApiKeyService` exists but has no public router. Recommended routes:

```
POST   /api/saas/projects/{project_id}/keys     — issue new key
GET    /api/saas/projects/{project_id}/keys     — list keys for project
GET    /api/saas/projects/{project_id}/keys/{id} — get key metadata (no raw key)
DELETE /api/saas/projects/{project_id}/keys/{id} — revoke key
```

All routes require operator/admin auth and org membership check.

---

## 8. Tests

Existing tests cover:
- Key generate → hash → authenticate round trip
- Revoked key rejected
- Wrong key returns None
- Constant-time comparison
- Key prefix display

See: `backend/tests/test_saas_router.py`, `backend/tests/test_p0_auth_tenant.py`.
