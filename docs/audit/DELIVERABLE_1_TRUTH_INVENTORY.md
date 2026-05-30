# Deliverable 1: Repository Truth Inventory

**Date:** May 30, 2026
**Method:** Direct file count via `find`, verified against `.gitignore` rules.

---

## Project File Counts (Excluding .venv, .git, __pycache__, .mypy_cache)

| Type | Count | Notes |
|------|-------|-------|
| Python files (`.py`) | 329 | Project source only (151 in `backend/app/`) |
| Test files (`test_*.py`) | 146 | In `backend/tests/` |
| Manual test files (`manual_*.py`) | 15 | Not collected by pytest |
| Benchmark files | 4 | In `backend/benchmarks/` (not `test_*.py` named) |
| Markdown files | 29 | Docs + root |
| JavaScript files | 452 | Mostly in `.agents/`, `.commandcode/` dirs |
| HTML files | 62 | Frontend + test fixtures |
| Config/deployment files | 27 | YAML, INI, Dockerfile, lock files, etc. |
| Script files | 24 | In `scripts/` |
| Frontend files | 22 | HTML + JS + CSS |
| Fixture HTML pages | 42 | In `backend/tests/fixtures/pages/` |
| Archive files | 12 | In `docs/archive/` |
| **Total project files** | ~600 | Excluding virtual env, git history, caches |

---

## Suspicious / Problematic Files

### Committed Secrets (on disk, NOT in git tracking)
| File | Issue |
|------|-------|
| `.env` | Contains real GROQ_API_KEY, database passwords, 3 API keys (all same value) |
| `.env.production` | Contains real database password, API keys, Grafana password |
| `.env.bak` | Backup of env file |

### Committed Runtime Artifacts (on disk)
| File | Issue |
|------|-------|
| `backend/data/worker_queue.db` | SQLite database with runtime state |
| `backend/data/jobs_state.db` | SQLite database with job state |
| `backend/data/jobs_state_test.db` | Test database |
| `backend/data/crawl_frontier.db` | Crawl frontier database |
| `logs/audit.log` | Runtime log file |
| `backend/logs/audit.log` | Runtime log file |

### Tracked in Git (safe examples)
| File | Status |
|------|--------|
| `.env.example` | ✅ Safe placeholder template |
| `.env.production.example` | ✅ Safe placeholder template |

---

## Duplicate / Overlapping Modules

None detected. Module structure is reasonably clean.

## Generated / Report Files

| File | Type |
|------|------|
| `docs/audit/DELIVERABLE_*.md` | Audit deliverables (these files) |
| `docs/archive/` | Historical/outdated documents |

## Large Files (>500KB, project-only)

- `.mypy_cache/` — Type checking cache (should be gitignored, is gitignored)
- `bin/docker-compose` — Binary tool (1.2MB)

## Files That Should Be Archived or Removed

| File | Reason |
|------|--------|
| `docs/archive/` contents | Already archived, evaluation needed for deletion |
| `backend/data/*.db` | Runtime state, should not be committed |
| `logs/*.log` | Runtime logs, should not be committed |

---

## Summary

The project is structurally clean. No committed secrets in git history (only example files tracked). The `.env` file exists on disk with real credentials — this is a security risk for anyone who clones the repo without a proper `.gitignore`. Runtime databases and logs on disk indicate the project was run locally but these should be added to `.gitignore` and cleaned.
