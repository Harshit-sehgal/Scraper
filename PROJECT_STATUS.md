# Project Status — DataForge Scraper

**Date:** May 30, 2026<br>
**Classification:** Truth-First Status Report<br>
**Overall Maturity:** ~58% (Pre-Production Candidate — Core Verified, Multiple Known Issues)

---

## ✅ Verified

- FastAPI backend starts and serves 55 API routes successfully.
- Python syntax is clean (`compileall` passes, 0 errors).
- Zero pyflakes warnings across all application code.
- Mypy static type checking passes with 0 errors (`--ignore-missing-imports`).
- 2,207 tests collected across 145 files.
- SQLite storage backend works for CRUD operations out of the box.
- 4 benchmark scripts renamed and collected by pytest.
- URL safety module has 16 passing tests preventing SSRF attacks.
- In-memory rate limiting operates correctly.
- Nginx reverse proxy configured with strict Content Security Policy (CSP).
- Prometheus metrics and Grafana dashboards configured.
- Job lifecycle (create, cancel, results, recycle bin) functions work.
- CSV/JSON/Excel export endpoints work.
- 42 fixture HTML pages for extraction testing.

## ⚠️ Partially Verified

- **Postgres support**: Code exists but tests require `--run-postgres` flag and a running container.
- **Execution accuracy**: Semantic pipeline and LLM bridge exist. Real accuracy depends on site structure.
- **Anti-bot evasion**: Basic evasion exists (`anti_bot_engine.py`). Real-world effectiveness is unknown.
- **CI pipeline**: Workflow file exists (`.github/workflows/ci.yml`) but was not validated in this audit.
- **Production startup gate**: Credential validation exists but depends on `DATAFORGE_ENV=production` being set.
- **Route-level access control**: `require_role` decorators exist, but all API keys in `.env.example` are empty — RBAC is only functional once users generate keys.

## 🔶 Implemented but Not Fully Validated

- **Semantic world state**: CRDT-based state management exists. Real-world behavior under load unknown.
- **Adaptive extraction**: Self-tuning extraction code exists but not stress-validated.
- **Selector discovery**: Automated selector discovery code exists but accuracy unmeasured.
- **Federation**: Sharded federation code exists but untested in multi-node deployment.
- **Crawl frontier**: Code exists.
- **Benchmark accuracy**: Metrics exist but hostile benchmark uses simulated data.
- **Frontend CSP compatibility**: Vendored assets exist, but browser rendering not verified against strict CSP.
- **Dashboard localStorage**: UI state stored in localStorage. Not suitable for public deployment without hardening.

## ❌ Known Issues

- **E01 — Test env isolation (🟢 Fixed)**: Conftest.py forces `DATAFORGE_STORAGE_BACKEND=sqlite` and clears `DATAFORGE_DATABASE_URL`. Residual ~40 failures only if conftest is bypassed (e.g., running outside pytest).
- **E03 — Credentials on disk (🔴 Critical)**: Real GROQ_API_KEY, DB passwords, Grafana password in `.env` on disk. Rotate immediately.
- **E05 — Manual test integration (🟠 High)**: 14 manual test scripts in `backend/tests/` not collected by pytest.
- **E06 — Dashboard localStorage (🟠 High)**: API key stored in `localStorage` — XSS vulnerability for public deployment.
- **E07 — Config centralization (🟠 High)**: Direct `os.getenv` calls remain in `state_store.py` and `__init__.py`, bypassing centralized config.
- **E08 — CDN reference in vendored assets (🟢 Fixed)**: Unused `tailwind.min.js` with CDN warning deleted. No breakage — file was not referenced anywhere.
- **E14 — pyflakes test dep (🟡 Medium)**: `test_pyflakes_fixes.py` depends on pyflakes being installed.
- **E15 — Event loop scope (🔵 Low)**: `asyncio_default_fixture_loop_scope = function` in pytest.ini may cause issues.
- **E16 — Hardcoded paths (🔵 Low)**: Some test files assume specific working directory.
- **E18/19 — Runtime artifacts (⚪ Cleanup)**: `backend/data/*.db` and `logs/*.log` on disk.
- **D10 naming collision (🟢 Fixed)**: `DELIVERABLE_10_FIELD_LAWS.md` renamed to `DELIVERABLE_10_FIELD_LAWS_LEGACY.md`.

## 🟠 Production Blockers

1. **RBAC requires user action** — API keys must be generated (`.env.example` has empty keys).
3. **No distributed rate limiting** — In-memory only, single-process.
4. **Grafana dashboard config** — Assumes datasource availability, not validated.
5. **Docker deployment not validated** — No CI test with actual `docker compose up`.

## 📊 Benchmark Limitations

| Benchmark | Classification | Evidence |
|-----------|---------------|----------|
| `test_benchmark_hostile.py` | Simulated | Uses fixture pages, not real hostile sites |
| `test_benchmark_smoke.py` | Offline import check only | `test_run_smoke_benchmark()` creates a single `SiteResult` — does not run real extraction |
| `test_benchmark_replay.py` | Synthetic | Replays Causality workload on mock data |
| `test_benchmark_longevity.py` | Simulated | Runs cycles on fixture data, not live |

All benchmarks are **collected by pytest** but none test real-world extraction against live websites.

## 🔬 Current Test Status

| Metric | Value |
|--------|-------|
| Tests collected | 2,207 |
| Test files | 145 |
| Python syntax | ✅ Clean |
| Pyflakes warnings | ✅ Zero |
| Benchmarks collected | ✅ 4/4 |
| Manual tests integrated | ⚠️ test_manual_tests.py exists (import validation) |
| Estimated passing (SQLite) | ~1,843 (E01 fix applied — conftest forces SQLite) |

## ✅ What Can Be Claimed Honestly

- "FastAPI backend imports successfully and serves 55 routes."
- "SQLite-based job storage and management works."
- "Playwright-based extraction works for configured sites."
- "The project has 2,207 tests covering most components."
- "In-memory rate limiting and SSRF protection exist."
- "Production deployment files exist but require validation."
- "The project is a pre-production candidate with known issues."

## ❌ What Must Not Be Claimed Yet

- "100% production ready" — Has known production blockers.
- "Fully self-healing" — Recovery handlers not stress-validated.
- "Works on any website" — Extraction depends on site structure.
- "Enterprise-grade security" — localStorage XSS, no distributed rate limiting.
- "All tests pass" unconditionally — passes with SQLite override; requires `DATAFORGE_STORAGE_BACKEND=sqlite`.
- "Fully secure" — Real credentials on disk, RBAC requires user action.
- "Complete" — Manual tests not integrated, benchmarks are simulated.

## Next Validation Steps

1. ✅ E01: Conftest.py already overrides `STORAGE_BACKEND=sqlite`. Ensure no residual `.env` interferes.
2. Fix E03: Rotate exposed credentials immediately
3. Integrate manual tests into pytest (E05)
4. Add CI pipeline validation
5. Run full test suite without `.env` to confirm zero env-bleed failures
6. Fix frontend localStorage risk for public deployment
7. Centralize remaining `os.getenv` calls
8. Add real-world extraction benchmarks
