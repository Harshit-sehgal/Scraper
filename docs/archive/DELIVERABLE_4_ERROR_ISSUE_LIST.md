# Deliverable 4: Error and Issue List

<div style="border: 2px solid #d24646; background: #fef6f6; padding: 1rem 1.2rem; border-radius: 12px; margin-bottom: 1.5rem;">
  <strong style="color: #972a2a; font-size: 0.95rem;">⚠ HISTORICAL DOCUMENT</strong><br>
  <span style="color: #607069; font-size: 0.85rem;">
    This archived deliverable was generated during a prior cleanup cycle. It is preserved for reference only.
    Do not treat it as current evidence. Always consult <code>PROJECT_STATUS.md</code> for the current truth source.
  </span>
</div>


**Date:** May 30, 2026

---

## Severity Levels

| Level | Meaning |
|-------|---------|
| 🔴 Critical | Blocks honest production readiness, security, or basic runtime |
| 🟠 High | Significant gap that weakens reliability or truthfulness |
| 🟡 Medium | Important but not blocking |
| 🔵 Low | Cleanup / nice-to-have |
| ⚪ Cleanup | Cosmetic or organizational |

---

## Issues Found

| ID | Severity | Area | File/Path | Problem | Evidence | Exact Fix |
|----|----------|------|-----------|---------|----------|-----------|
| E01 | 🔴 Critical | Test/Env | `.env` + `conftest.py` | `.env` sets `DATAFORGE_STORAGE_BACKEND=postgres` and `DATAFORGE_ENV=production`. Conftest sets env to development but doesn't clear STORAGE_BACKEND. Results in ~40+ test failures when Postgres isn't running. | Test run shows `RuntimeError: could not translate host name \"db\" to address` | `conftest.py` must also set `os.environ["DATAFORGE_STORAGE_BACKEND"] = "sqlite"` and unset `DATAFORGE_DATABASE_URL` |
| E02 | 🔴 Critical | Security | `.env` | Same API key used for user, operator, AND admin roles (`0dd9362f...` repeated). RBAC is effectively useless. | Direct file read | Generate 3 separate keys. Regenerate all as proper random values. |
| E03 | 🔴 Critical | Security | `.env` | Real GROQ_API_KEY, database passwords, and Grafana password are stored in a committed `.env` file on disk. Anyone with filesystem access can use them. | File exists on disk | Add `.env` to `.gitignore` (already is). Rotate all keys immediately. |
| E04 | 🟠 High | Test/Bench | `backend/benchmarks/*.py` | 4 benchmark files are NOT collected by pytest (not named `test_*.py`). Benchmark claims cannot be verified automatically. | pytest collection confirms only `test_*.py` files collected | Rename to `test_benchmark_hostile.py`, `test_benchmark_replay.py`, etc. Or document as manual-only. |
| E05 | 🟠 High | Test | `backend/tests/manual_*.py` | 15 manual test files are NOT collected by pytest. They exist as ad-hoc scripts with no CI integration. | `find` + `pytest --collect-only` comparison | Either convert to proper tests or move to `scripts/` with clear documentation. |
| E06 | 🟠 High | Security | `frontend/` | Dashboard stores API key in `localStorage`. XSS vulnerability if any script injection occurs. | Code inspection of `frontend/js/api.js` | Add `httpOnly` cookie option or document as internal-only tool. |
| E07 | 🟠 High | Config | Multiple | Direct `os.getenv()` calls in 9+ locations bypass centralized config. `config.py` exists but isn't the single source of truth. | `grep -rn 'os.getenv.*DATAFORGE_' backend/app/` | Migrate all env reads to `config.py` |
| E08 | 🟠 High | Security | `nginx.conf` + `frontend/` | Nginx enforces strict CSP (`script-src 'self'`), but frontend vendored assets have CDN references. Potential breakage. | `grep` shows Tailwind CDN reference in vendored file | Remove CDN references from vendored files, or add `'unsafe-inline'` intentionally with docs. |
| E09 | 🟡 Medium | Production | `scripts/check_prod_env.py` | Production env validation exists as an **optional script**. Not a hard startup gate. Production can start with placeholder secrets. | Code inspection | Add validation to `main.py` startup when `DATAFORGE_ENV=production` |
| E10 | 🟡 Medium | Docs | Multiple | Post-CSP-fix docs still reference old CDN-based state in some places. | Cross-reference check | Update remaining stale CSP mentions |
| E11 | 🟡 Medium | Security | All API routes | No route-level access control. All routes are protected by the same API key middleware. Operator/admin roles are not enforced at route level. | Route enumeration + code inspection of middleware | Add `@requires_role("operator")` / `@requires_role("admin")` decorators |
| E12 | 🟡 Medium | Production | `Dockerfile` | Python packages pinned in `requirements.lock.txt` but Docker uses `requirements.txt` which may have unpinned versions. | Dockerfile inspection | Switch Docker to use lock file |
| E13 | 🟡 Medium | Production | `docker-compose.prod.yml` | No healthcheck on application container. Container health is not verified by orchestration. | File inspection | Add `healthcheck` block to app service |
| E14 | 🟡 Medium | Test | `test_pyflakes_fixes.py` | Test exists that checks pyflakes is clean. If pyflakes isn't installed, test either fails or is skipped. | Test file code | Document as optional dependency |
| E15 | 🔵 Low | Config | `pytest.ini` | `asyncio_default_fixture_loop_scope = function` — may cause event loop issues with async fixtures that create their own loops. | Config file | Consider changing to `module` scope |
| E16 | 🔵 Low | Test | Multiple test files | Some test files have hardcoded paths that assume a specific working directory. | Code inspection | Make paths relative to test file location |
| E17 | 🔵 Low | Docs | Archive files | 12 files in `docs/archive/` with stale data (old test counts, old claims). | File inspection | Clean or remove outdated archives |
| E18 | ⚪ Cleanup | Repo | `backend/data/*.db` | Runtime databases committed to disk (not tracked in git, but present). | `find` output | Add to `.gitignore` if not already |
| E19 | ⚪ Cleanup | Repo | `logs/*.log` | Runtime logs committed to disk. | `find` output | Add to `.gitignore` |

---

## Root Cause Analysis

The single largest cause of test failures is **E01**: `.env` with `DATAFORGE_STORAGE_BACKEND=postgres` and `DATAFORGE_ENV=production` bleeds into the test environment. The conftest.py clears API keys and sets env to development, but doesn't clear the storage backend. This causes ~40 tests to fail when Postgres isn't running.

The single largest security issue is **E02 + E03**: All three API keys are identical, and real credentials exist in `.env` on disk.

The single largest documentation issue is **E04 + E05**: Benchmarks and manual tests are not integrated into the testing framework, so claims made about them cannot be verified automatically.
