# Route Auth Matrix

**Generated from the registered FastAPI app. Do not edit generated rows by hand.**

**Command:** `python3 scripts/generate_route_auth_matrix.py`

**API route rows:** 149
**Unknown auth rows:** 0
**Unknown tenant-scope rows:** 0

Unknown auth or tenant-scope rows must be tracked as candidate issues.

| Method | Path | Public/Protected | Required Role | Route Dependency | Middleware Protected | Tenant Scoped | Test Coverage | Boundary | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/auth-profiles` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/auth-profiles/{profile_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/auth-profiles/{profile_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/complete-login` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/revoke` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/start-login` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/validate` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/billing/checkout` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/billing/stub-return/{plan_tier}/{request_id}` | protected | authenticated-user | none | yes | no | yes | stable | protected by global /api middleware; no route-level role dependency |
| `GET` | `/api/billing/subscriptions` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/billing/subscriptions/{customer_id}` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/billing/webhook` | protected | authenticated-user | none | yes | no | yes | stable | protected by global /api middleware; no route-level role dependency; mutation role should be reviewed |
| `POST` | `/api/discover` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/exports/batch` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/intelligence/analyze-url` | protected | authenticated-user | none | yes | no | unknown | stable | protected by global /api middleware; no route-level role dependency |
| `GET` | `/api/jobs` | protected | authenticated-user | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs` | protected | operator-or-admin | require_plan_limit.<locals>.dependency, require_role | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/jobs/cleanup/terminal` | protected | admin | require_role | yes | yes | yes | stable | require_role/admin-only dependency |
| `DELETE` | `/api/jobs/{job_id}` | protected | admin | require_role | yes | yes | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/jobs/{job_id}` | protected | authenticated-user | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs/{job_id}/backfill-metadata` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/jobs/{job_id}/cancel` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/events` | protected | authenticated-user | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/export/csv` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/export/excel` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/export/json` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/jobs/{job_id}/reclean` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/results` | protected | authenticated-user | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/operator/dashboard` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `DELETE` | `/api/operator/denylist` | protected | admin | require_role_with_user | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/operator/denylist` | protected | operator-or-admin | require_role_with_user | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/operator/denylist` | protected | admin | require_role_with_user | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/operator/health` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/operator/mode` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `POST` | `/api/operator/mode` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/operator/predictions` | protected | authenticated-user | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator/user |
| `GET` | `/api/operator/predictions/{domain}` | protected | authenticated-user | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator/user |
| `DELETE` | `/api/recycle_bin` | protected | admin | require_role | yes | yes | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/recycle_bin` | protected | authenticated-user | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `DELETE` | `/api/recycle_bin/{job_id}` | protected | admin | require_role | yes | yes | yes | stable | require_role/admin-only dependency |
| `POST` | `/api/recycle_bin/{job_id}/restore` | protected | admin | require_role | yes | yes | yes | stable | require_role/admin-only dependency |
| `POST` | `/api/saas/aup/accept` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/aup/status` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/email-verification/send` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/email-verification/status` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/email-verification/verify` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/invitations/pending` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/invitations/{invitation_id}/respond` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/me` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `DELETE` | `/api/saas/memberships/{membership_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/orgs` | protected | operator-or-admin | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/orgs/{org_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs/{org_id}` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/orgs/{org_id}/invitations` | protected | operator-or-admin | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/saas/orgs/{org_id}/invitations` | protected | operator-or-admin | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs/{org_id}/members` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/orgs/{org_id}/projects` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/password-reset/request` | protected | authenticated-user | none | yes | no | yes | stable | protected by global /api middleware; no route-level role dependency; mutation role should be reviewed |
| `POST` | `/api/saas/password-reset/reset` | protected | authenticated-user | none | yes | no | yes | stable | protected by global /api middleware; no route-level role dependency; mutation role should be reviewed |
| `GET` | `/api/saas/plan` | protected | authenticated-user | require_role_with_user | yes | no | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/projects` | protected | operator-or-admin | require_aup_accepted, require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/projects/{project_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/saas/projects/{project_id}` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/projects/{project_id}/keys` | protected | authenticated-user | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/projects/{project_id}/keys` | protected | operator-or-admin | require_aup_accepted, require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/projects/{project_id}/keys/{key_id}` | protected | operator-or-admin | require_role_with_user | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/saas/signup` | public | none | none | no | no | yes | stable | explicit API middleware exemption |
| `GET` | `/api/saas/usage` | protected | authenticated-user | require_role_with_user | yes | no | yes | stable | route dependency accepts admin/operator/user |
| `GET` | `/api/scheduled` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/scheduled` | protected | operator-or-admin | require_aup_accepted, require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/scheduled/{job_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scheduled/{job_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `PUT` | `/api/scheduled/{job_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scheduled/{job_id}/changes` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/schema/suggest` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/browser` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/config` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/scraper/diagnostics` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/economics` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/domain/{domain}` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/domains` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/legacy` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/health/summary` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/scraper/memory/stats` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/scraper/ml/learn` | protected | operator-or-admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator |
| `POST` | `/api/scraper/ml/optimize/domain/{domain}` | protected | operator-or-admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator |
| `GET` | `/api/scraper/ml/optimize/domain/{domain}/history` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/scraper/regressions` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/scraper/regressions/generate-all-tests` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/scraper/regressions/{entry_id}` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/scraper/regressions/{entry_id}/generate-test` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `POST` | `/api/scraper/selectors/cleanup` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/scraper/selectors/domain/{domain}` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/selectors/low-confidence` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/selectors/stats` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/stats` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/domain/{domain}` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `POST` | `/api/scraper/strategy/evolve/{domain}` | protected | operator-or-admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/recommend/{domain}` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `POST` | `/api/scraper/strategy/record` | protected | operator-or-admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/report` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `DELETE` | `/api/scraper/telemetry` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/scraper/telemetry` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/scraper/trends` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/scraper/trends/{domain}` | protected | authenticated-user | require_role, verify_experimental_enabled | yes | no | yes | experimental | route dependency accepts admin/operator/user |
| `DELETE` | `/api/session` | public | none | none | no | no | yes | stable | explicit API middleware exemption |
| `POST` | `/api/session` | public | none | none | no | no | yes | stable | explicit API middleware exemption |
| `GET` | `/api/session/me` | public | none | none | no | no | yes | stable | explicit API middleware exemption |
| `GET` | `/api/system/acquisition/telemetry` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/agency` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/audit-log` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/system/crystalline` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `POST` | `/api/system/csp-violations` | public | none | none | no | no | yes | stable | explicit API middleware exemption |
| `GET` | `/api/system/diagnostics/export` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `GET` | `/api/system/domain-policy` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/export/knowledge` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/history/topology` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/manifest` | protected | authenticated-user | require_role | yes | no | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/system/merge/knowledge` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/observability` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/rate-limit-stats` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/system/refactor/compress` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/replay/chain` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/replay/events` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/replay/status` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/retention/config` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `POST` | `/api/system/retention/enforce` | protected | admin | require_role | yes | no | yes | stable | require_role/admin-only dependency |
| `POST` | `/api/system/scheduler/step` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/search` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `GET` | `/api/system/status` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/system/storage/status` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/system/topology` | protected | admin | require_role, verify_experimental_enabled | yes | no | yes | experimental | require_role/admin-only dependency |
| `POST` | `/api/url/analyze` | protected | operator-or-admin | require_role | yes | no | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/user/data` | protected | authenticated-user | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator/user |
| `POST` | `/api/workflow-drafts/from-url-analysis` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/{draft_id}/detect-fields` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/{draft_id}/manual-mapping` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/workflows` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/workflows` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `DELETE` | `/api/workflows/{workflow_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `PATCH` | `/api/workflows/{workflow_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `PUT` | `/api/workflows/{workflow_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/workflows/{workflow_id}/preview` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `POST` | `/api/workflows/{workflow_id}/run` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}/runs` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}` | protected | operator-or-admin | require_principal | yes | yes | yes | stable | route dependency accepts admin/operator |
