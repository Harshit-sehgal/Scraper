# DataForge Scraper - Codebase Quality and Security Audit Report
**Date:** 2026-06-27
**Status:** Complete Audit Report

## 1. Executive Summary & File Inventory Statistics
This report presents a file-by-file audit of the DataForge Scraper codebase, evaluating security posture, adherence to tenant isolation rules, API authorization consistency, and developer tooling reliability.

A full repository scan accounts for the following file counts (compiled via `python3 artifacts/audit/gen_full_ledger.py` and recorded in the audit inventory):
- **Total files inventoried:** 32,408
- **Project-owned files:** 1,064
- **Project-owned files deeply inspected:** 1,054
- **Skipped generated/vendor/binary/cache/log/archive files:** 31,354
- **Files needing follow-up:** 7

The baseline quick validation check (`python3 scripts/validate_local.py --quick`) passes all 12 stages, and the security checks pass 8/8 stages, confirming that the overall architecture remains robust. However, this audit has identified three P1-level and three P2-level issues that have been registered in the issue ledger.

---

## 2. Adherence to Core Safety & Isolation Rules

### A. Centralized Authentication and Authorization
- **Status:** Mostly Compliant (with 1 critical exemption issue).
- **Mechanism:** Authentication checks are centralized in `backend/app/utils/rbac.py` through `resolve_auth_context` and route dependencies (`require_principal`, `require_role`). Individual route handlers do not implement ad-hoc authorization parses.
- **Findings/Gaps:** A critical bug (`P1-AUTH-PASSWORD-RESET-001`) was identified where public password reset routes return HTTP 403 Forbidden in production environments because they are missing from the `api_key_middleware` exclusions list in `backend/app/middlewares.py`.

### B. Tenant, User, and Project Isolation
- **Status:** Partially Compliant (with 3 isolation bypass issues).
- **Mechanism:** Resource endpoints (jobs, results, exports, workflows) filter queries and mutate data via the `can_access_scoped_resource` helper which enforces owner/org/project match.
- **Findings/Gaps:**
  1. `P1-SEC-TENANT-001`: Billing subscription endpoints `GET /api/billing/subscriptions` and `GET /api/billing/subscriptions/{customer_id}` only check role-level `ADMIN` or `OPERATOR` without checking organization or project boundaries, exposing customer records across tenants to any operator-level API key.
  2. `P1-ARCH-QUOTA-001`: Usage ledger and plan enforcer track quotas by `user_id` (API key fingerprint) rather than `org_id` or `project_id`, enabling plan bypass by generating multiple keys.
  3. `P2-SAAS-TENANT-BYPASS-001`: SaaS project and organization deletion/view endpoints in `backend/app/saas/router.py` check creator `user_id` or basic organization membership instead of key-scoped project/org bounds, allowing scoped keys to view or delete resources of other projects.
  4. `P2-SEC-GUARDIAN-001`: The cross-tenant guardian `guard_cross_tenant` in `backend/app/utils/cross_tenant_guard.py` is implemented and unit-tested but is completely orphaned (not called in production code), offering zero runtime query-level leak protection.

### C. No CAPTCHA/Anti-Bot Bypass or Unsafe Scraping
- **Status:** Compliant.
- **Mechanism:** The scraper contains `AntiBotEngine` and `BrowserPool` which perform bot-detection checks and adjust request timings/proxy rotation/stealth navigator characteristics without attempting to solve CAPTCHAs, perform login bypasses, or scrape private/unauthorized systems.

### D. Stable vs. Experimental Boundary
- **Status:** Compliant.
- **Mechanism:** Research and experimental modules live in `backend/app/research/` and are gated by `settings.ENABLE_EXPERIMENTAL_ROUTES` at registry, lifespan loading, and router mount levels. The static boundary check passes with 0 violations.

---

## 3. Detailed Audit Findings (6 Newly Registered Issues)

### P1-AUTH-PASSWORD-RESET-001
- **File Path:** `backend/app/middlewares.py`
- **Function/Lines:** `api_key_middleware` (lines 127-180)
- **Evidence:** Under `DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false`, a POST request to `/api/saas/password-reset/request` or `/api/saas/password-reset/reset` without credentials returns HTTP 403 Forbidden.
- **Why it matters:** Public/unauthenticated users cannot invoke password reset flows in staging/production where dev auth is disabled.
- **Impact:** Broken password-reset feature in production.
- **Recommended Fix:** Add `/api/saas/password-reset/request` and `/api/saas/password-reset/reset` to the exemptions list in `api_key_middleware`.

### P1-SEC-TENANT-001
- **File Path:** `backend/app/billing/webhooks.py` (lines 590-611)
- **Function/Lines:** `list_subscriptions` and `get_subscription`
- **Evidence:** Endpoints utilize `require_role([UserRole.ADMIN, UserRole.OPERATOR])` without checking tenant matching constraints (`org_id` / `project_id`).
- **Why it matters:** Projects scoped with operator API keys can view all subscriptions and customer details across the system.
- **Impact:** Cross-tenant customer billing record exposure, violating tenant isolation rules.
- **Recommended Fix:** Modify dependencies to use `require_principal` and enforce matching `customer_id` to the principal's `org_id` or `user_id`.

### P1-ARCH-QUOTA-001
- **File Path:** `backend/app/utils/usage_ledger.py` and `backend/app/plan_enforcer.py`
- **Function/Lines:** `_quota_key` and `get_quota`
- **Evidence:** Quotas are cached and evaluated against the `user_id` key fingerprint instead of `org_id` or `project_id`.
- **Why it matters:** A single organization can bypass monthly quota limits by creating multiple keys.
- **Impact:** Plan-limit bypass vulnerability.
- **Recommended Fix:** Aggregate and enforce usage quotas at the `org_id` or `project_id` level.

### P2-SAAS-TENANT-BYPASS-001
- **File Path:** `backend/app/saas/router.py`
- **Function/Lines:** `delete_organization`, `delete_project`, and `get_project`
- **Evidence:** Enforce basic membership or creator matches on `user_id` without matching `project_id`/`org_id` constraints of the API key.
- **Why it matters:** A project-scoped key can read or delete other projects in the same organization.
- **Impact:** Cross-project resource exposure or deletion.
- **Recommended Fix:** Implement `can_access_scoped_resource` constraints on these routes.

### P2-SEC-GUARDIAN-001
- **File Path:** `backend/app/utils/cross_tenant_guard.py`
- **Function/Lines:** `guard_cross_tenant`
- **Evidence:** Function is defined and tested but has no imports or calls in repository query code.
- **Why it matters:** The multi-tenant safety barrier is orphaned and provides no runtime query leak check.
- **Impact:** Zero runtime query-level leak protection.
- **Recommended Fix:** Integrate `guard_cross_tenant` into database retrieval code (e.g., list operations).

### P2-DEV-LOGGING-JSON-ERROR-001
- **File Path:** `scripts/generate_route_inventory.py`
- **Function/Lines:** `_raw_method_paths` (line 307)
- **Evidence:** Subprocess runs the FastAPI application and prints startup rate-limiter logs in JSON format to stdout, breaking JSON route array parsing.
- **Why it matters:** Tooling and documentation regeneration scripts fail unless run with manual env overrides.
- **Impact:** Breaks developer documentation workflow.
- **Recommended Fix:** Inject `DATAFORGE_LOG_LEVEL=ERROR` into the subprocess environment dictionary.

---

## 4. Verification Methods and Execution Evidence
- **Ledger Compilation Check:** Run `python3 artifacts/audit/gen_full_ledger.py` to ensure consistency.
- **Codebase Quick Validation:** Run `python3 scripts/validate_local.py --quick`.
- **Security Check Validation:** Run `python3 scripts/validate_local.py --security`.
