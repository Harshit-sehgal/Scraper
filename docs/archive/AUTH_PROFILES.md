# DataForge Scraper — Auth Profiles

Date: 2026-06-13
Commit: `7d47045`

Safe, domain-locked, encrypted browser sessions for user-authorized logged-in scraping.
Implementation: `backend/app/routers/auth_profiles.py`, `backend/app/models.py`, `backend/app/utils/encryption.py`.

---

## 1. Purpose

Auth Profiles allow users to scrape pages behind login walls — sites they are authorized to access — without exposing passwords or raw cookies. DataForge stores an encrypted Playwright `storage_state` scoped to a single domain.

---

## 2. How It Works

```
1. User creates an Auth Profile for a domain (e.g., example.com)
2. DataForge opens a controlled browser session on example.com
3. User logs in manually (DataForge never sees the password)
4. Server captures the Playwright storage_state (cookies, localStorage)
5. Server encrypts storage_state and stores it with the profile
6. User selects auth_profile_id when creating a job or workflow
7. Scraper decrypts storage_state and creates a Playwright context
8. Scraper runs the job/workflow with the authenticated session
9. If the session expires, DataForge detects it and asks the user to reconnect
10. User can revoke/delete the profile at any time
```

---

## 3. Current Implementation

### Model (`backend/app/models.py`)

```python
class AuthProfile(BaseModel):
    id: str
    name: str                          # Human-readable name
    description: str                   # Optional description
    user_id: str                       # Owner
    org_id: str                        # Organization
    project_id: str                    # Project
    domain: str                        # Restricted domain
    encrypted_storage_state: str       # AES-256-GCM encrypted state
    encryption_key_version: str        # Key version for rotation
    status: AuthProfileStatus          # pending_login / active / expired / revoked / failed
    failure_reason: str                # Reason for failure
    created_at: str
    updated_at: str
    expires_at: str | None
    last_validated_at: str | None
    last_used_at: str | None
    usage_count: int
```

### Router (`backend/app/routers/auth_profiles.py`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth-profiles` | Operator/Admin | Create a new auth profile (status: pending_login) |
| `GET` | `/api/auth-profiles` | Operator/Admin | List accessible profiles |
| `GET` | `/api/auth-profiles/{id}` | Operator/Admin | Get profile metadata |
| `DELETE` | `/api/auth-profiles/{id}` | Operator/Admin | Delete profile permanently |
| `POST` | `/api/auth-profiles/{id}/start-login` | Operator/Admin | Initiate browser login flow |
| `POST` | `/api/auth-profiles/{id}/complete-login` | Operator/Admin | Store encrypted storage_state |
| `POST` | `/api/auth-profiles/{id}/validate` | Operator/Admin | Check if session is still active |
| `POST` | `/api/auth-profiles/{id}/revoke` | Operator/Admin | Revoke profile, clear stored state |

All responses strip `encrypted_storage_state` via `_safe_profile()`.

### Encryption (`backend/app/utils/encryption.py`)

- **Algorithm:** AES-256-GCM (authenticated encryption)
- **Key source:** `DATAFORGE_ENCRYPTION_KEY` environment variable (base64-encoded 32-byte key)
- **Key versioning:** `DATAFORGE_ENCRYPTION_KEY_VERSION` supports rotation
- **Safe failure:** In development, a test key is derived automatically. In production, missing key raises `EncryptionError`.
- **Format:** Base64-encoded JSON object containing `v` (version), `c` (ciphertext), `n` (nonce), `t` (tag)

---

## 4. Tenant Isolation

- Profile creation stamps `user_id`, `org_id`, `project_id` from the authenticated principal.
- List/get/delete enforce `can_access_scoped_resource()`.
- Cross-org persistent keys cannot see another org's profiles.

---

## 5. What Is Implemented

- ✅ Auth profile model with owner/org/project fields
- ✅ CRUD endpoints with tenant isolation
- ✅ `encrypted_storage_state` never exposed in API responses
- ✅ **Encryption at rest (AES-256-GCM)**
- ✅ **Login flow endpoints (start-login, complete-login)**
- ✅ **Validation and revoke endpoints**
- ✅ **Domain lock enforcement in get_decrypted_storage_state**
- ✅ **Session expiry detection (timestamp-based)**
- ✅ `last_used_at` / `usage_count` tracking
- ✅ P0 tenant isolation tests (33 tests pass)
- ✅ Threat model documented

---

## 6. What Is Not Yet Implemented

| Feature | Status |
|---------|--------|
| Playwright browser automation for login capture | ❌ Backend foundation ready; live browser integration pending |
| Live expiry detection (redirect, 401/403, page text) | ❌ Timestamp-based only; live detection pending |
| Auth profile selection in workflow/job creation UI | ❌ |
| Frontend auth profile management page | ❌ |

---

## 7. Security Properties

| Property | Status |
|----------|--------|
| Storage state encrypted at rest | ✅ AES-256-GCM |
| Storage state never in API responses | ✅ Verified |
| Domain-locked (profile can only be used on its domain) | ✅ Enforced in get_decrypted_storage_state |
| Tenant-isolated (cross-org denied) | ✅ Verified |
| Revocable (delete removes from store) | ✅ Verified |
| Audit-logged (create/delete events) | ⚠️ Partial |
| No passwords stored | ✅ By design |
| No raw cookies in logs | ✅ By design |

---

## 8. Tests

- `backend/tests/test_auth_profiles.py` — Auth profile CRUD, encryption, login flow, validation, revoke
- `backend/tests/test_encryption.py` — Encryption/decryption roundtrip, edge cases
- `backend/tests/test_p0_auth_tenant.py` — Cross-org tenant isolation tests
