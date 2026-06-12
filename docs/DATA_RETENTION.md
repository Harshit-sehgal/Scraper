# DataForge Scraper — Data Retention

Date: 2026-06-13
Commit: `7d47045`

Data lifecycle management for scraped data, exports, and account data. Current state: partial. Implementation exists for recycle bin; full retention policy and enforcement remain follow-up work.

---

## 1. Current Retention Capabilities

### Job Data
- Jobs store results in SQLite/Postgres (configurable).
- Recycle bin: jobs can be soft-deleted → moved to recycle bin → restorable within a window → permanently deleted after expiry.
- Export files: compressed results stored on disk.

### Recycle Bin Flow
```
DELETE /api/jobs/{id}           → soft-delete (mark deleted, move to recycle bin)
GET /api/recycle-bin            → list deleted jobs
POST /api/recycle-bin/{id}/restore → restore job and associated data
DELETE /api/recycle-bin/{id}    → permanent deletion
```

Recycle bin respects tenant isolation — users can only see their own org/project's deleted jobs.

---

## 2. What Needs To Be Defined

### Retention Periods

| Data Type | Proposed Default | Rationale |
|-----------|-----------------|-----------|
| Active job results | Until job deleted or 90 days | User needs time to review and export |
| Recycle bin | 30 days after soft-delete | Grace period for accidental deletion |
| Export files | 7 days after download | Exports are ephemeral by nature |
| Audit logs | 1 year | Compliance and incident investigation |
| Usage records | 1 year | Billing disputes and audit |
| Auth profiles (encrypted) | Until user revokes | Session material is user-controlled |

### Hard Delete

Permanent deletion must cascade:
- Job results (disk files + DB rows)
- Associated events and logs
- Export files generated from the job
- Any workflow preview snapshots

### Export Log Retention
- Export metadata (who, what, when, format, record count) retained per audit policy.
- Export file contents subject to the 7-day default.

---

## 3. Account and Project Deletion

### Delete My Account (Not Yet Implemented)
1. User requests account deletion.
2. All user's jobs, workflows, auth profiles are permanently deleted.
3. Membership records are removed from orgs.
4. If user is the last owner of an org, org is deleted (or ownership transferred).
5. Audit log of deletion is retained.

### Delete Project (Not Yet Implemented)
1. All jobs in the project are deleted (soft → recycle → hard).
2. All workflows in the project are deleted.
3. All API keys for the project are revoked.
4. Project is permanently deleted.
5. Audit event records the deletion.

---

## 4. Compliance Considerations

- **GDPR:** Users must be able to request data deletion. The "delete my account" flow satisfies this.
- **Data minimization:** Scraped data should not be retained indefinitely. Configure retention windows.
- **Right to access:** Users can export their own data before deletion.
- **Audit trail:** All deletions are logged for compliance evidence.

---

## 5. Current Gaps

| Feature | Status |
|---------|--------|
| Recycle bin for jobs | ✅ Implemented |
| Tenant-isolated recycle bin | ✅ Enforced |
| Configurable retention windows | ❌ Not implemented |
| Automatic expiry / cleanup | ❌ Not implemented |
| "Delete my account" flow | ❌ Not implemented |
| "Delete project" cascade | ❌ Not implemented |
| Export file cleanup | ❌ Not implemented |
| Audit log retention policy | ❌ Not defined |

---

## 6. Recommended Implementation Order

1. Add configurable retention window env vars.
2. Implement automatic cleanup of expired recycle bin items.
3. Add "delete project" endpoint with cascade.
4. Add "delete account" endpoint with cascade and audit.
5. Add export file cleanup after retention period.
6. Document retention policy for operators.

---

## 7. Tests Needed

- Recycle bin expiry and hard delete
- Project deletion cascades to jobs/workflows/keys
- Account deletion cascades to all owned resources
- Cross-tenant cannot restore another org's job
- Audit log events for all deletion paths
