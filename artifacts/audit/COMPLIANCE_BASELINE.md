# Compliance Baseline

Date: 2026-06-12
Commit: `7d47045`
Scope: Prompt 7 acceptable-use and compliance baseline.

## Evidence Inspected

- `docs/SAFETY_AND_ACCEPTABLE_USE.md`
- `backend/app/url_safety.py`
- `backend/app/admin_denylist.py`
- `backend/app/crawl_policy.py`
- `backend/app/audit_logger.py`
- `backend/app/routers/exports.py`
- `backend/app/storage_interface.py`
- `backend/app/postgres_repository_base.py`
- `backend/tests/test_p1_compliance_denylist.py`
- `backend/tests/test_audit_logger.py`

## Control Matrix

| Control | Status | Evidence | Gap |
| --- | --- | --- | --- |
| Lawful accessible-web scope | documented | `docs/SAFETY_AND_ACCEPTABLE_USE.md` | Needs product UI copy and admin policy |
| No bypass policy | documented | safety doc and global contract | Needs enforcement in future workflow/auth-profile work |
| Robots/crawl policy | partial | `backend/app/crawl_policy.py` best-effort robots awareness | Robots behavior not launch-gated |
| Domain denylist | partial | `backend/app/admin_denylist.py`, tests | Admin UI/process not fully verified |
| Per-domain limits | partial | crawl policy settings | Load/abuse test not run |
| Audit events | partial | audit logger and tests | Coverage map incomplete |
| Data retention | partial | recycle bin/delete paths exist | Formal retention policy and tests missing |
| Delete/export logs | partial | export access/audit paths exist | Full audit coverage not mapped |
| Abuse flags | partial | denylist/cooldown controls | Abuse workflow and operator process missing |
| Admin controls | partial | operator/admin routes exist | Full route policy review remains open |

## Compliance Status

Partial. The repo has useful safety controls, but production compliance
is not established until acceptable-use policy, retention/deletion,
audit coverage, domain blocking, and abuse workflows are enforced and
tested end to end.
