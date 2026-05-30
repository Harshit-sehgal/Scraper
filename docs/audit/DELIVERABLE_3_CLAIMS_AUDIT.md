# Deliverable 3: Claims Audit

**Date:** May 30, 2026
**Method:** Cross-reference between documentation, code, test output, and runtime behavior.

---

## Truth Classification

| Status | Meaning |
|--------|---------|
| ✅ Verified | Directly proven by code, passing tests, or runtime evidence |
| ⚠️ Partial | Some evidence exists but incomplete |
| 🔶 Claimed | Documentation says it, no strong proof found |
| ❌ False | Documentation contradicts code or behavior |
| ❓ Unknown | Could not verify (missing deps, services, or credentials) |

---

## Claims Table

| Claim | Source | Truth | Evidence | Action |
|-------|--------|-------|----------|--------|
| "Postgres production-ready" | Multiple docs | ❌ False | Postgres tests skip by default; `.env` uses Postgres mode but no container running | Fix env/test isolation |
| "1,884 tests, all pass" | PROJECT_STATUS.md | ❌ False | 2,207 collected, many fail due to Postgres env leak | Update count + fix env |
| "RBAC with operator/admin roles" | Docs, code | ⚠️ Partial | RBAC code exists but all 3 keys are identical value | Fix key separation |
| "Strict CSP enforced" | SECURITY.md | ⚠️ Partial | Nginx CSP is strict. Dashboard uses vendored assets but CDN refs exist | Audit all HTML/JS |
| "Rate limiting" | Docs | ✅ Verified | In-memory rate limiter exists. Works per-process. NOT distributed. | Document limitation |
| "SSRF protection" | Docs, code | ✅ Verified | `url_safety.py` blocks private IPs, localhost, metadata endpoints | Confirmed by code |
| "Anti-bot resilience" | Docs | 🔶 Claimed | `anti_bot_engine.py` exists but no real-world validation | Add disclaimer |
| "Self-healing" | Docs | 🔶 Claimed | Recovery handlers exist but stress tests are simulated | Needs real testing |
| "Works on any website" | (implied) | ❌ False | Requires specific selectors/config. Not universal. | Remove this claim |
| "100% extraction accuracy" | (nowhere explicit) | ✅ Not claimed | No doc currently claims this | Keep honest |
| "Enterprise-grade security" | (nowhere explicit) | ✅ Not claimed | No doc currently claims this | Keep honest |
| "Real-time streaming dashboard" | IMPLIED | ❌ False | Frontend polls APIs, no WebSocket/SSE | Document as polling |
| "Semantic extraction" | Docs, code | ⚠️ Partial | Code exists for semantic pipeline/LLM bridge. Real accuracy unknown. | Needs benchmark |
| "Benchmark methodology" | Docs | ❌ False | 4 benchmark files not collected by pytest; some use simulated data | Fix naming/methodology |
| "Dashboard works in production" | IMPLIED | ⚠️ Partial | Files exist but CSP/CDN conflict exists | Fix CSP or document |
| "CI/CD pipeline" | .github/workflows/ | ⚠️ Partial | CI workflow exists (ci.yml). Haven't verified it runs. | Verify CI |
| "Centralized configuration" | CLAIMED | ⚠️ Partial | `config.py` exists but 9+ direct `os.getenv` calls in modules | Migrate to config |
| "Production startup gates" | CLAIMED | ❌ False | `check_prod_env.py` exists but is optional script, not hard gate | Add hard gate |
| "Type-safe" | IMPLIED | ⚠️ Partial | mypy passes with `--ignore-missing-imports`. Typing coverage partial. | Document scope |
| "Duplicate env names resolved" | Code | ⚠️ Partial | `DATAFORGE_STATE_FILE` used — no duplicate found | Verify docs match |

---

## Summary of Overclaims Found

1. **Test count and pass rate** — documented as 1,884 passing, actually 2,207 total with failures
2. **Postgres readiness** — claimed validated, actually fails without running container
3. **RBAC** — claimed with role separation, actually all keys are same value
4. **CSP** — claimed fully resolved, but CDN references still exist in some frontend files
5. **Benchmarks** — Simulated metrics presented without clear "simulated" label
6. **Real-time dashboard** — Dashboard polls, doesn't stream
7. **Production readiness** — Missing hard secret validation gate
