# Data Retention and Deletion Policy

**Status:** Implemented defaults (pre-production). Legal review still recommended before public launch.

## Default Windows

Configured via `app.utils.data_retention.get_retention_config()`:

| Data class | Env var | Default |
| --- | --- | --- |
| Completed terminal jobs | `DATAFORGE_RETENTION_DAYS_COMPLETED` | 90 days |
| Recycle bin items | `DATAFORGE_RETENTION_DAYS_RECYCLE` | 30 days |
| Idempotency keys | `DATAFORGE_RETENTION_DAYS_IDEMPOTENCY` | 7 days |

## Enforcement

- Admin endpoint: `POST /api/system/retention/enforce` (dry-run supported)
- Implementation: `app.utils.data_retention.enforce_retention`
- Tests: `backend/tests/test_retention.py`

## Hard Delete vs Recycle Bin

- User-facing delete moves jobs to recycle bin (soft delete).
- Recycle bin purge and retention enforcement perform hard deletes from storage.
- Cross-tenant isolation is enforced before any delete/restore/export path.

## Export and Audit Logs

- Export access is audit-logged (`log_rbac_event` / export usage ledger).
- Audit log rotation: 10 MB × 5 files under `logs/audit.log` (see `audit_logger.py`).

## Operator Checklist

1. Set retention env vars for your environment before launch.
2. Run a dry-run retention enforce in staging and verify counts.
3. Document customer-facing retention in your SaaS terms.

See also: `docs/SAFETY_AND_ACCEPTABLE_USE.md`, `artifacts/audit/COMPLIANCE_BASELINE.md`.
