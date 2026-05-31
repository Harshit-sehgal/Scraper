# Deliverable 11: Exact Fix Plan

**Date:** May 30, 2026

---

## Priority Order

Issues are ordered by impact: stop false claims first, fix security, fix tests, fix production, fix docs.

---

## Fix 1: Test Environment Isolation (E01)

**Severity:** 🔴 Critical
**Area:** Test/Env leakage
**Files affected:** `backend/tests/conftest.py`

### Problem
`.env` sets `DATAFORGE_STORAGE_BACKEND=postgres` and `DATAFORGE_ENV=production`. Conftest sets `DATAFORGE_ENV=development` and clears API keys, but doesn't clear the storage backend. This causes ~40 test failures when Postgres isn't running.

### Implementation
In `backend/tests/conftest.py`, add after line 82:
```python
os.environ["DATAFORGE_STORAGE_BACKEND"] = "sqlite"
os.environ.pop("DATAFORGE_DATABASE_URL", None)
```

### Validation
```bash
PYTHONPATH=backend python3 -m pytest -q --tb=line | tail -3
```
Expected: Test failures drop from ~40 to near 0 (excluding Postgres-skipped tests).

---

## Fix 2: Separate API Keys (E02)

**Severity:** 🔴 Critical
**Area:** Security/RBAC
**Files affected:** `.env`, `.env.example`

### Problem
All three API keys (DATAFORGE_API_KEY, DATAFORGE_OPERATOR_API_KEY, DATAFORGE_ADMIN_API_KEY) are the same value `0dd9362f0dd9362f0dd9362f0dd9362f0dd9362f0dd9362f0dd9362f0dd9362f`. RBAC is non-functional.

### Implementation
Generate truly random keys:
```bash
python3 -c "import secrets; [print(f'{name}={secrets.token_hex(32)}') for name in ['DATAFORGE_API_KEY', 'DATAFORGE_OPERATOR_API_KEY', 'DATAFORGE_ADMIN_API_KEY']]"
```
Replace in `.env` and `.env.example`.

### Validation
```bash
grep DATAFORGE_API_KEY .env | sort -u | wc -l
```
Expected: 3 (each key is unique).

---

## Fix 3: Production Startup Gate (E09)

**Severity:** 🟠 High
**Area:** Production readiness
**Files affected:** `backend/app/main.py`

### Problem
Production env validation (`check_prod_env.py`) is an optional script. Production can start with placeholder secrets.

### Implementation
Add at the top of `main.py` (before creating the FastAPI app):
```python
def _validate_production_env():
    if os.environ.get("DATAFORGE_ENV") != "production":
        return
    from app.utils.prod_security_validator import validate_production_environment
    errors = validate_production_environment()
    if errors:
        msg = "\n  - ".join(["Production startup blocked:"] + errors)
        print(msg, flush=True)
        sys.exit(1)
```

### Validation
```bash
DATAFORGE_ENV=production DATAFORGE_API_KEY= PYTHONPATH=backend python3 -c "from app.main import _validate_production_env; _validate_production_env()"
```
Expected: Exits with error.

---

## Fix 4: Conftest API Key Cleanup (E02 related)

**Severity:** 🟠 High
**Area:** Test/RBAC
**Files affected:** `backend/tests/conftest.py`

### Problem
Conftest clears API keys to allow unauthenticated test access, but the keys are the same value anyway.

### Implementation
After line 82, add explicit overrides that work regardless of .env values:
```python
os.environ["DATAFORGE_API_KEY"] = "test-api-key"
os.environ["DATAFORGE_OPERATOR_API_KEY"] = "test-operator-key"
os.environ["DATAFORGE_ADMIN_API_KEY"] = "test-admin-key"
```

### Validation
```bash
PYTHONPATH=backend python3 -m pytest backend/tests/test_rbac.py -q --tb=line
```
Expected: RBAC tests pass.

---

## Fix 5: Route-Level Access Control (E11)

**Severity:** 🟡 Medium
**Area:** Security
**Files affected:** All router files

### Problem
No `@requires_role()` decorator enforcement on routes. Any valid key can access any endpoint.

### Implementation (if using existing RBAC utils)
Add decorators to sensitive routes:
- Operator routes: scraper config, telemetry, trends, selectors, ML, strategy, diagnostics
- Admin routes: scheduler, operator mode, system config

For initial fix, document the gap and add explicit role checks to the highest-sensitivity endpoints:
- `POST /api/scraper/ml/optimize/domain/{domain}` — operator+
- `POST /api/scraper/strategy/evolve/{domain}` — operator+
- `POST /api/operator/mode` — admin only
- `GET /api/scraper/diagnostics` — admin only

---

## Fix 6: Rename Benchmarks to test_*.py (E04)

**Severity:** 🟡 Medium
**Area:** Testing
**Files affected:** `backend/benchmarks/*.py`

### Problem
4 benchmark files are not collected by pytest (not named `test_*.py`).

### Implementation
```bash
cd backend/benchmarks
mv hostile.py test_benchmark_hostile.py
mv smoke.py test_benchmark_smoke.py
mv replay.py test_benchmark_replay.py
mv longevity.py test_benchmark_longevity.py
```

### Validation
```bash
PYTHONPATH=backend pytest backend/benchmarks/ --collect-only -q
```
Expected: Benchmarks appear in collection.

---

## Fix 7: Docker Lock File (E10)

**Severity:** 🟡 Medium
**Area:** Dependencies
**Files affected:** `Dockerfile`

### Problem
Docker uses `requirements.txt` instead of `requirements.lock.txt` for pinned versions.

### Implementation
In `Dockerfile`, change:
```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt
```
to:
```dockerfile
COPY requirements.lock.txt requirements.txt
RUN pip install -r requirements.txt
```

---

## Fix 8: Container Healthcheck (E13)

**Severity:** 🟡 Medium
**Area:** Production deployment
**Files affected:** `docker-compose.prod.yml`

### Implementation
Add to the `dataforge` service:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

## Fix 9: Direct os.getenv Migration (E07)

**Severity:** 🔵 Low
**Area:** Config
**Files affected:** Multiple (9+ locations)

### Implementation
For each direct `os.getenv("DATAFORGE_*")` call:
1. Add the config value to `config.py`
2. Import from `config` instead of using `os.getenv`
3. Keep direct `os.getenv` as deprecated with a comment

Locations to migrate:
- `routers/exports.py:71` — DATAFORGE_WORKER_QUEUE
- `routers/jobs.py:43,300,367` — DATAFORGE_WORKER_QUEUE
- `state_store.py:43` — DATAFORGE_STATE_FILE
- `__init__.py:8` — DATAFORGE_DOTENV_PATH
- `url_safety.py:46` — DATAFORGE_SMOKE_TEST_MODE
- `worker_queue.py:879` — DATAFORGE_QUEUE_BACKEND
- `postgres_repository.py:56,64` — DATAFORGE_DATABASE_URL, DATAFORGE_ENV

---

## Fix 10: Documentation Updates (D8)

**Severity:** 🔵 Low
**Area:** Docs

### Implementation
1. Rewrite `README.md` with corrected, honest content (see D9)
2. Rewrite `PROJECT_STATUS.md` with truth-first content (see D10)
3. Delete stale archive files:
   - `docs/archive/RELEASE_NOTES.md`
   - `docs/archive/RELEASE_CANDIDATE_CHECKLIST.md`
   - `docs/archive/DEPLOYMENT_VALIDATION_CHECKLIST.md`
   - `docs/archive/audit/AUDIT_SUMMARY.md`

---

## Fix 11: Add CI Gates

**Severity:** 🟡 Medium
**Area:** CI/CD

### Implementation
Update `.github/workflows/ci.yml` to include:
- `python -m compileall -q backend scripts`
- `PYTHONPATH=backend python3 -m pyflakes backend/app/`
- `DATAFORGE_STORAGE_BACKEND=sqlite PYTHONPATH=backend python3 -m pytest -q`
- `PYTHONPATH=backend python architecture_validator.py`

---

## Summary: Fix Order

| Order | Fix | Severity | Effort | Impact |
|-------|-----|----------|--------|--------|
| 1 | Fix conftest.py (E01) | 🔴 Critical | 1 line | Unblocks all tests |
| 2 | Generate separate keys (E02) | 🔴 Critical | 3 lines | Enables RBAC |
| 3 | Production startup gate (E09) | 🟠 High | 15 lines | Prevents deployment with bad config |
| 4 | Conftest key cleanup | 🟠 High | 3 lines | Ensures test isolation |
| 5 | Route-level RBAC (E11) | 🟡 Medium | Varies | Enforces access control |
| 6 | Rename benchmarks (E04) | 🟡 Medium | 4 mv commands | Integrates benchmarks |
| 7 | Docker lock file (E10) | 🟡 Medium | 1 line | Ensures reproducible builds |
| 8 | Container healthcheck (E13) | 🟡 Medium | 6 lines | Validates app health |
| 9 | os.getenv migration (E07) | 🔵 Low | Varies | Centralizes config |
| 10 | Documentation cleanup | 🔵 Low | Rewrite+delete | Honest docs |
| 11 | CI gates | 🟡 Medium | ~10 lines | Automated validation |
