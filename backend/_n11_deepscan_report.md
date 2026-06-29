# N+11 Deep-Scan Report: PII Log Redaction Gaps

**Date:** 2026-06-29
**Scope:** `backend/app/billing/*.py`, `backend/app/saas/router.py`, `backend/app/routers/*.py`, `backend/app/subscription*.py`, `backend/app/auth/*.py`
**Scanner:** grep/rg pattern search for raw customer_id/tenant_id/email/user_id in logger/print/raise/f-string calls

---

## Findings

### 1. HIGH — billing/service.py:378 — raw customer_id in logger.warning

**Line:**
```python
logger.warning(
    "Billing is not configured — denying balance check for customer=%s. "
    "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET env vars must be set.",
    customer_id,
)
```

**Fix:** Replace `customer_id,` with `_redact_id(customer_id),` (function already exists at line 108 of the same file).

---

### 2. MEDIUM — saas/router.py:129 — raw user_id in logger.debug

**Line:**
```python
logger.debug("AUP user lookup failed for %s: %s", user_id, exc)
```

**Fix:** Add `from app.utils.log_redaction import redact_pii` and wrap: `redact_pii(str(user_id)), exc`

---

### 3. MEDIUM — saas/router.py:901 — raw user.email in logger.debug

**Line:**
```python
logger.debug("Email verification token created for %s", user.email)
```

**Fix:** Use `redact_pii(user.email)` to mask the email address, or truncate to domain-only.

---

### 4. MEDIUM — saas/router.py:1171 — raw body.email in logger.debug

**Line:**
```python
logger.debug("Password reset token created for %s", body.email)
```

**Fix:** Use `redact_pii(body.email)` to mask the email address.

---

### 5. MEDIUM — saas/router.py:908 — email in audit log_job_event details

**Line:**
```python
details={"email": user.email},
```

**Fix:** Replace `user.email` with `redact_pii(user.email)` or store only a domain hash.

---

### 6. MEDIUM — saas/router.py:1177 — email in audit log_job_event details

**Line:**
```python
details={"email": body.email},
```

**Fix:** Replace `body.email` with `redact_pii(body.email)` or store only a domain hash.

---

### 7. MEDIUM — saas/router.py:1849 — raw user_id in logger.debug

**Line:**
```python
logger.debug("Quota context resolution failed; falling back to user_id: %s", user_id)
```

**Fix:** Wrap with `redact_pii(str(user_id))`.

---

### 8. LOW — routers/user_data.py:132,159,168,177,213,217 — raw user_id in logger calls

**Lines:**
```python
132:  logger.warning("Failed to delete jobs for user %s: %s", user_id, e)
159:  logger.warning("Failed to delete workflows for user %s: %s", user_id, e)
168:  logger.warning("Failed to delete auth profiles for user %s: %s", user_id, e)
177:  logger.warning("Failed to delete scheduled jobs for user %s: %s", user_id, e)
213:  logger.warning("Failed to clean up SaaS identity for user %s: %s", user_id, e)
217:  user_id,  (in logger.info)
```

**Fix:** Import `redact_pii` from `app.utils.log_redaction` and wrap each `user_id` argument. These are internal UUIDs rather than directly-identifiable PII, but in a multi-tenant SaaS context, user_id is a correlatable identifier across audit/log aggregates.

---

## Summary

| Severity | Count | Files |
|----------|-------|-------|
| HIGH     | 1     | billing/service.py |
| MEDIUM   | 6     | saas/router.py |
| LOW      | 6     | routers/user_data.py |
| **Total**| **13**| |

**Key shared utility:** `app.utils.log_redaction.redact_pii()` can be imported in all affected files. `billing/service.py` already has its own `_redact_id()` which should also be applied at line 378.

**Previously-fixed lines confirmed clean:** billing/service.py lines 288, 321, 345, 387, 395, 403, 411 all correctly use `_redact_id(customer_id)`. billing/webhooks.py lines 343, 546, 563, 575, 577, 581, 594, 596, 679 all correctly use `_redact_id(customer_id)`.
