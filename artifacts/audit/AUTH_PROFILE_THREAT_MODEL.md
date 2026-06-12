# DataForge Scraper — Auth Profile Threat Model

Date: 2026-06-13
Commit: `7d47045`
Scope: Threat assessment for the Auth Profiles feature (Prompt 10). Planning only; no implementation changes.

---

## 1. Threat: Stolen Auth Profile (encrypted_storage_state at rest)

**Impact:** If an attacker gains access to the database, they could decrypt `encrypted_storage_state` and impersonate the user on the target domain.

**Mitigation:**
- Use authenticated encryption (e.g., AES-256-GCM with a key from env/secret manager).
- Encryption key must never be committed to the repository.
- Key versioning allows rotation without re-encrypting all profiles.

**Current state:** `encrypted_storage_state` field exists but encryption is not implemented. Field defaults to empty string. Marked as follow-up work.

**Remaining risk:** Without encryption, the field name is aspirational. Must implement before production use.

---

## 2. Threat: Cross-Tenant Auth Profile Access

**Impact:** User A could use User B's auth profile to scrape a domain they are not authorized to access, or view session metadata.

**Mitigation (implemented):**
- Auth profile CRUD stamps `user_id`, `org_id`, `project_id` from authenticated principal.
- All read/mutation/delete routes enforce `can_access_scoped_resource()`.
- Cross-org persistent keys cannot see another org's profiles.

**Current state:** P0-fixed in Prompt 3. Tests: `test_p0_auth_tenant.py` verifies cross-org denial.

**Remaining risk:** Low. Tenant isolation is enforced at the route level.

---

## 3. Threat: Domain Misuse

**Impact:** A user creates an auth profile for `example.com`, but the profile's session cookies could potentially be used to access `admin.example.com` or `api.example.com` if the session scope is too broad.

**Mitigation:**
- Auth profile stores the target domain.
- Workflow/job runner must verify domain match before using the profile.
- Domain lock prevents profile use on unrelated domains.

**Current state:** Domain field exists in model. Domain match verification is not yet implemented in the runner.

**Remaining risk:** Medium. Domain lock must be enforced before auth profiles are used in production workflows.

---

## 4. Threat: Log Leakage (Cookies/Tokens in Logs)

**Impact:** If `storage_state` (containing cookies, localStorage, session tokens) is written to application logs, it could be exfiltrated via log aggregation.

**Mitigation:**
- `encrypted_storage_state` is never exposed in API responses (`_safe_profile()` strips it).
- The router never logs the raw or encrypted state.
- Validation scripts redact common secret patterns.

**Current state:** Implemented. API responses strip the field. Logger does not log it.

**Remaining risk:** Low. Verified by `test_storage_state_not_exposed`.

---

## 5. Threat: Database Leakage (Encrypted Storage State)

**Impact:** Even encrypted, a database dump contains all auth profile metadata (domains, names, timestamps) which reveals scraping targets.

**Mitigation:**
- Database access restricted to authorized operators.
- Audit log tracks all auth profile access.
- Retention/deletion policy allows users to delete profiles.

**Current state:** Audit logger exists. Deletion endpoint exists (DELETE `/api/auth-profiles/{id}`). Database access controls are operational (not code-level).

**Remaining risk:** Medium. No automatic cleanup of deleted profile data from backups.

---

## 6. Threat: Frontend Exposure of Storage State

**Impact:** If the frontend renders `encrypted_storage_state` in the UI, it could be exposed via browser extensions, screenshots, or XSS.

**Mitigation:**
- API never returns `encrypted_storage_state` in responses.
- Frontend should never request or display it.

**Current state:** API strips the field. No frontend auth profile management page exists yet.

**Remaining risk:** Low. Must verify when frontend auth profile UI is built.

---

## 7. Threat: Session Expiry (Stale Profile Used)

**Impact:** A user attempts to scrape with an expired auth profile. The scraper fails silently or returns degraded results.

**Mitigation:**
- Expiry detection: detect login redirects, 401/403 responses, "session expired" page text.
- Mark profile as `expired` and return clear user message.
- `last_validated_at` and `expires_at` fields in model.

**Current state:** Not implemented. Model has `expires_at` field but no detection logic.

**Remaining risk:** High. Without expiry detection, users get confusing failures.

---

## 8. Threat: Revocation Failure

**Impact:** A user revokes an auth profile but the session cookies remain valid on the target site, allowing continued scraping.

**Mitigation:**
- Revocation deletes the profile from the store (in-memory or DB).
- The runner cannot load a deleted profile.
- Audit log records revocation.

**Current state:** DELETE endpoint exists and removes from `_auth_profiles` store. Audit log records deletion.

**Remaining risk:** Low. Revocation is effective at the DataForge level. Target-site session may persist but cannot be used without the stored profile.

---

## 9. Threat: Operator/Admin Access to Auth Profiles

**Impact:** An operator or admin could enumerate all auth profiles and their target domains, revealing customer scraping activity.

**Mitigation:**
- Admin/operator all-access is opt-in and explicitly tested.
- Audit log records admin access to auth profiles.
- Policy: operators should only access profiles for incident response.

**Current state:** `require_principal([ADMIN, OPERATOR])` on all auth profile routes. Admin can see all profiles. This is by design but should be audited.

**Remaining risk:** Low-Medium. Acceptable for internal/admin tooling. Must add audit events for admin profile access.

---

## 10. Threat: Backup Exposure

**Impact:** A backup of the identity store contains `encrypted_storage_state` fields. If the encryption key is also backed up (or the field is unencrypted), the backup becomes a high-value target.

**Mitigation:**
- Encryption key stored separately from database backups.
- Backup files encrypted at rest.
- Restore drill verifies profile data integrity without exposing plaintext.

**Current state:** Backup scripts exist but not encrypted. `encrypted_storage_state` is not actually encrypted.

**Remaining risk:** High. Must implement encryption before production backups.

---

## Summary

| Threat | Severity | Status |
|--------|----------|--------|
| Stolen auth profile (no encryption) | High | Not implemented |
| Cross-tenant access | Low | Fixed (P0) |
| Domain misuse | Medium | Domain lock pending |
| Log leakage | Low | Fixed |
| Database leakage | Medium | Partial |
| Frontend exposure | Low | API strips field |
| Session expiry | High | Not implemented |
| Revocation failure | Low | Fixed |
| Operator access | Low-Medium | Acceptable with audit |
| Backup exposure | High | Not implemented |
