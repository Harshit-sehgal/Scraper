# DataForge Scraper — Audit Logs

Date: 2026-06-13
Commit: `7d47045`

Comprehensive audit logging for security, compliance, and incident investigation. Implementation: `backend/app/audit_logger.py`.

---

## 1. Audit Event Types

| Function | Purpose | Example Events |
|----------|---------|---------------|
| `log_auth_event()` | Authentication attempts | Login success/failure, API key auth, session validation |
| `log_rbac_event()` | Access control decisions | Role check passed/denied, tenant scope permit/deny |
| `log_admin_action()` | Operator/admin operations | Org create, project delete, member remove, key revoke |
| `log_data_access()` | Data retrieval | Export download, result access, job detail view |
| `log_job_event()` | Job lifecycle | Job created, running, completed, failed, cancelled |
| `log_system_event()` | System operations | Migration, startup, shutdown, health check failure |

---

## 2. Audit Event Schema

Every audit event includes:

```json
{
  "event_id": "uuid",
  "timestamp": "2026-06-13T12:00:00Z",
  "event_type": "auth_failure | rbac_deny | admin_action | ...",
  "actor_user_id": "user-123",
  "actor_role": "operator",
  "action": "job_create | export_download | key_revoke | ...",
  "target_type": "job | export | api_key | organization | ...",
  "target_id": "resource-id",
  "org_id": "org-456",
  "project_id": "project-789",
  "domain": "example.com (if applicable)",
  "outcome": "success | denied | failed",
  "metadata": { "details": "redacted" },
  "source_ip": "192.0.2.1 (if available)",
  "user_agent": "DataForge-CLI/1.0 (if available)"
}
```

---

## 3. Covered Resources

| Resource | Create | Read | Update | Delete | Denied Access |
|----------|--------|------|--------|--------|--------------|
| Jobs | ✅ | ✅ | — | ✅ | ✅ |
| Results | — | ✅ | — | — | ✅ |
| Exports | ✅ | ✅ | — | — | ✅ |
| Workflows | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auth Profiles | ✅ | ✅ | — | ✅ | ✅ |
| Scheduled Jobs | ✅ | ✅ | — | ✅ | ✅ |
| API Keys | ✅ | — | — | ✅ | — |
| Organizations | ✅ | ✅ | — | — | — |
| Projects | ✅ | ✅ | — | — | — |
| Memberships | ✅ | ✅ | — | ✅ | — |

---

## 4. Auth Failure Auditing

All auth failures are logged with:
- Request path and method
- Auth method attempted (API key / session cookie / bearer)
- Reason: `invalid_key`, `revoked_key`, `expired_session`, `malformed_token`
- No raw keys or tokens in the audit log

---

## 5. Tenant Denial Auditing

When a cross-tenant access is denied:
- `log_rbac_event()` records the attempted resource, owner org/project, and caller org/project
- Outcome: `denied`
- No resource data is exposed

Covered denial paths:
- Cross-org job access
- Cross-org export attempt
- Cross-org workflow access
- Cross-org auth profile access
- Cross-org scheduled job access

---

## 6. Security Properties

- **File-based:** Audit events are written to rotating log files in `AUDIT_LOG_DIR`.
- **Structured:** Each event is a JSON line, machine-parseable.
- **Redacted:** Sensitive values (tokens, keys, passwords) are never written to audit logs.
- **Immutable:** Audit log is append-only; old events are not modified.
- **Tenant-scoped:** Each event carries `org_id` and `project_id` for isolation.

---

## 7. Audit Log Querying

Currently file-based only. Future: database-backed audit store with:
- `GET /api/admin/audit` — admin audit log query
- Filter by org_id, project_id, event_type, date range
- Export audit log

---

## 8. Coverage Gaps

Known gaps to fill:
- Quota denial audit (audit when usage is blocked)
- URL safety block audit (audit when unsafe URL is rejected)
- AUP acceptance audit (exists, logged as `job_event`)
- Export download audit (exists)

See `artifacts/audit/ISSUE_LEDGER.md` — `P1-AUDIT-COVERAGE-001`.

---

## 9. Tests

- `backend/tests/test_audit_logger.py` — unit tests for event creation, parsing, reset
- `backend/tests/test_audit_logger_integration.py` — integration tests for auth, RBAC, admin, data access events
- `backend/tests/test_p0_auth_tenant.py` — cross-tenant denial audit test
