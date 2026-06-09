# DataForge Scraper — 100/100 SaaS Readiness Progress

This tracker is the running evidence file for the `stabilize/phase-0-truth` work.
It is updated as each small, test-backed change lands. The goal is to move the
project from **55/100 → 100/100 SaaS readiness** using the master plan in
`Instructions_for_ai/DataForge_100_100_SaaS_Master_Plan.md`.

> **Source of truth:** master plan + verified issue backlog (`DataForge_Issue_Backlog.csv`).
> Static candidates (`DataForge_Static_Issue_Candidates.csv`) and the 10k matrix
> (`DataForge_10000_SaaS_Readiness_Work_Items.csv`) are triage inputs, not confirmed bugs.

## Operating rules (from `DataForge_Coding_Agent_100_100_Prompt.txt`)

1. Do not trust docs unless a command verifies them.
2. Do not add features before closing P0/P1 stability, security, test, and truth issues.
3. Do not call unverified matrix rows confirmed bugs. Confirm by code + test.
4. Never use live internet/DNS in unit/API tests unless explicitly marked `integration`/`network`.
5. Never hold sync locks across `await`.
6. Keep experimental modules behind flags.
7. Every PR includes: tests, command output, docs update if behavior changed, rollback notes.
8. Prefer one issue per change. Do not rewrite large files without characterization tests.
9. When in doubt, stop adding code and write the failing test first.

## Phase 0 — freeze truth and create the safe working base (Weeks 1-2)

Goal: make the repo safe for coding agents and humans.

Acceptance gate:

- [ ] `pytest backend/tests/test_api_regressions.py -vv -x` completes quickly
- [ ] Full `pytest --collect-only` passes
- [ ] No unmarked unit/API test performs real DNS or live internet access
- [ ] Stable route docs match route inventory with experimental routes disabled

### Phase 0 work items

| # | Item | Status | Evidence | Commit |
|---|------|--------|----------|--------|
| 0.1 | `make doctor` + `scripts/doctor.py` (Python, tools, env, browser) | ✅ | 3 doctor tests pass, all required checks pass | `f4d3a12` |
| 0.2 | Global pytest-timeout in `pyproject.toml` (per-test + per-file) | ✅ | `--timeout=30` in addopts; 4 characterization tests pass | this commit |
| 0.3 | Missing test markers added (`unit`, `api`, `network`, `slow`) | ✅ | Markers registered in `pyproject.toml` + `conftest.py` | this commit |
| 0.4 | `conftest.py` autouse: block live DNS in unmarked tests (M1) | ✅ | 3 dns_isolation tests pass, 20 url_safety tests pass in 0.14s (was hanging) | this commit |
| 0.5 | Refactor `app/url_safety.py` to accept injected DNS resolver | pending | — | — |
| 0.6 | `make doctor` validates the new invariants | pending | — | — |
| 0.7 | Stable vs experimental API doc split (C1) | ✅ | 5 split tests pass; 42 stable routes, 77 experimental, 35 in diff | this commit |
| 0.8 | Generated current-status doc (replaces stale `CODE_REVIEW_BUGS.md`) (C3) | pending | — | — |

## Phase 1 — close P0 blockers (Month 1)

| # | Item | Status | Evidence | Commit |
|---|------|--------|----------|--------|
| 1.1 | Refactor router dependencies into injected runtime services (A1) | pending | — | — |
| 1.2 | Fix restore lock across `await` (B1) | pending | — | — |
| 1.3 | Run full suite under timeout, prove green (A2) | pending | — | — |
| 1.4 | Move `socket.getaddrinfo` off the event loop (M2) | pending | — | — |

## Phase 0 starting snapshot (2026-06-09)

- Branch created from `main` @ `cc1c9bf`.
- WIP on `fix/repo-stabilization-pass-1` preserved as `stash@{0}`.
- Existing `pyproject.toml` already lists `pytest-timeout>=2.3.0` in dev deps,
  but it is **not** enabled in `addopts` (no global timeout) and several
  markers from the master plan (`unit`, `api`, `network`, `slow`) are missing.
- `backend/app/url_safety.py` calls `socket.getaddrinfo` synchronously in
  multiple code paths; tests in `backend/tests/test_url_safety.py` exercise
  these paths and can hang on real DNS.
- `backend/app/routers/jobs_write.py` has 14+ `with manager.lock:` blocks,
  several wrapping async I/O — this is the B1 surface.

## How this tracker is updated

- Each Phase 0 work item is a single commit.
- The "Evidence" column is filled in with the actual command output and test
  count once the change is verified.
- When an item is closed, the row's Status flips to ✅ and the commit SHA
  is recorded.
