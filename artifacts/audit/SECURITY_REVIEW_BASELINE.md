# Security Review Baseline

Date: 2026-06-12
Commit: `7d47045`
Scope: Prompt 7 P1 baseline. This is not a full penetration test.

## Evidence Inspected

- `backend/app/utils/rbac.py`
- `backend/app/auth/session.py`
- `backend/app/middlewares.py`
- `backend/app/main.py`
- `backend/app/url_safety.py`
- `backend/app/admin_denylist.py`
- `backend/app/audit_logger.py`
- `backend/app/config/_security.py`
- `backend/app/utils/prod_security_validator.py`
- `scripts/check_prod_env.py`
- `frontend/js/api.js`
- `backend/tests/test_frontend_no_web_storage_for_keys.py`
- `backend/tests/test_p1_compliance_denylist.py`
- `backend/tests/test_audit_logger.py`

## Command Evidence

| Command | Exit | Result |
| --- | ---: | --- |
| `bandit -r backend || true` | 0 | No issues identified; 58,634 LOC scanned; 44 specifically disabled potential issues reported by Bandit output |
| `pip-audit || true` | 0 | Found 60 vulnerability records in 21 packages in the current Python environment, plus unauditable non-PyPI/system packages |

## Review Matrix

| Area | Status | Evidence | Gap |
| --- | --- | --- | --- |
| Auth/session | partial | central `resolve_auth_context`, signed revocable session cookies | Full auth-profile model contract still failing |
| API key handling | partial | constant-time env-key compare, persistent SaaS key lookup | Project dependency audit remains red |
| Cookie flags | partial | session cookies set `httponly`, `secure`, `samesite=strict` | Production secret proof not run |
| CSRF | partial | strict same-site cookie and API auth middleware | No explicit CSRF token model verified |
| CORS | partial | production wildcard CORS fail-closed in `main.py` and checker | Target deployment origins unverified |
| Secret/log redaction | partial | validation redaction, diagnostics sanitizer, network payload redaction | Need centralized log-redaction review |
| SSRF/URL safety | partial | scheme/port/internal IP/internal TLD/metadata checks | DNS rebinding and redirect chains need continued tests |
| Internal IP blocking | partial | `url_safety.py` rejects loopback/private/non-global IPs | Smoke mode allowlist must stay staging-only |
| Export access | partial | P0 export tenant isolation fixed and tested | Audit coverage depth still needs review |
| Tenant isolation | partial | P0 tests and route matrix exist | `/api/saas/plan` tenant scope remains candidate |
| Audit logging | partial | audit logger covers auth/RBAC/admin/data/job/system events | Full resource coverage not mapped |
| Rate limiting | partial | middleware and DB-backed promotion exist | Load/abuse tests not verified |
| Quota enforcement | partial | P0 regression tests pass | Production plan enforcement not launch-gated |
| Dependency vulnerabilities | failing | `pip-audit` reports 60 vulnerability records | Clean project-env audit and upgrades/triage needed |
| Frontend token storage | partial | `test_frontend_no_web_storage_for_keys.py` exists | Frontend auth E2E remains candidate |
| CSP | partial | report-only CSP middleware and endpoint exist | Blocking CSP policy not verified |
| subprocess usage | partial | operational scripts use hardcoded command vectors in several places | Keep Bandit and manual review in CI |
| `shell=True` | not verified clean | Prompt 7 did not prove zero use globally | Add grep/static invariant if needed |
| `verify=False` | not verified clean | Prompt 7 did not prove zero use globally | Add grep/static invariant if needed |
| raw cookie/session logging | partial | network capture redaction tests exist | Full logging audit still needed |

## Security Status

Security baseline is partial. Bandit is clean in this environment, but
dependency audit is red and production/staging security must not be
claimed until the dependency findings and environment-specific gates
are triaged.
