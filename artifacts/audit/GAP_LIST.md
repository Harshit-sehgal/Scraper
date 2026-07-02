# Gap List — Scraper SaaS MVP Audit (2026-06-30)

Generated from fresh verification against current code, tests, and command output.

## Goal 1 — Reproducible Setup: 85/100 ✅
| Check | Status | Detail |
|-------|--------|--------|
| validate_local.py --quick | ✅ 12/12 | Compile, architecture, research boundary, deps, p0 tests, OpenAPI |
| pip install -e ".[dev]" | ✅ (venv needed) | Expected on Debian — documented |
| npm ci | ✅ | 74 packages, 1 low vuln |
| npm run build | ✅ | 110.5KB CSS < 200KB (F-FRONTEND-001) |
| npm run lint | ✅ | stylelint + eslint + prettier all pass |
| npm test | ✅ | 36 files, 458 tests pass |
| playwright install | ⚠️ | Needs explicit `playwright install chromium` |

## Goal 2 — Core Scraping Flow: 82/100 ✅
| Check | Status | Detail |
|-------|--------|--------|
| Job lifecycle APIs | ✅ | create, list, get, cancel, reclean, delete, restore, diff, quality |
| URL validation/SSRF | ✅ | 19 SSRF + private IP tests, denylist, audit logging |
| Export APIs | ✅ | CSV, JSON, Excel, batch export, binary download |
| Status tracking | ✅ | pending→running→completed/canceled/empty_result, events endpoint |
| Results endpoint | ✅ | /api/jobs/{id}/results with pagination, search |
| Preview endpoint | ✅ | /api/scraper/preview (dry-run) |
| Test coverage | ✅ | 156 tests pass (lifecycle+exports+security core) |
| **Gap** | ⚠️ | No direct "create job → run job → check status → get results" E2E API test integrated in quick validation |

## Goal 3 — Frontend Product Path: 75/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Build passes | ✅ | esbuild outputs JS/CSS chunks + font |
| Lint passes | ✅ | stylelint, eslint, prettier |
| Vitest tests | ✅ | 458 tests, 36 files |
| index.html | ⚠️ 2618 lines | Oversized single-file HTML dashboard |
| CSS | ⚠️ 110KB | Under 200KB limit but still large |
| JS files | ✅ | Modular files (analyzer, results, form, jobs, workflows, etc.) |
| **Gap** | ❌ | No product mode UI — static dashboard is "internal-only" and experimental-centric |
| **Gap** | ❌ | Frontend has Playwright E2E config but tests run against mocks, not real app |

## Goal 4 — Security/Tenant Safety: 83/100 ✅
| Check | Status | Detail |
|-------|--------|--------|
| Auth/RBAC | ✅ | UserRole enums (ADMIN, OPERATOR, VIEWER), require_role deps |
| API keys | ✅ | API-key auth helpers, per-project key management tests |
| Tenant isolation | ✅ | User ID, org ID, project ID scoping in job reads |
| SSRF protection | ✅ | 19 tests: loopback, cloud metadata, bad schemes, internal TLDs, ports, restricted IPs, empty URLs, redirect-to-private |
| Rate limits | ✅ | CrawlPolicyEngine, domain rate limiting |
| Audit logs | ✅ | SSRF audit logging, access logs |
| Body limits | ⚠️ | Not explicitly tested — need to verify |
| Unsafe URL blocking | ✅ | Denylist, validate_public_http_url |
| **Gap** | ⚠️ | No explicit test showing VIEWER cannot hit admin routes |

## Goal 5 — Data/Export Reliability: 78/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Export formats | ✅ | CSV, JSON, Excel (XLSX) |
| Export tests | ✅ | test_exports_router.py, test_batch_exports.py, test_export_signing.py |
| Result schema consistency | ✅ | SchemaField, FieldType, ScrapeAttemptResult |
| Source URL in export | ✅ | final_url in ScrapeAttemptResult |
| Scrape time in export | ⚠️ | completed_at present but not explicitly verified in export tests |
| **Gap** | ⚠️ | No test verifying CSV content matches JSON content |
| **Gap** | ⚠️ | No test verifying Excel XLSX integrity |

## Goal 6 — Production Readiness (Docker): 72/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Dockerfile | ✅ | Multi-stage build, Playwright deps, dev/prod targets |
| docker-compose.yml | ✅ | Valid syntax, "dataforge" service |
| docker-compose.prod.yml | ✅ | Valid (requires DATAFORGE_IMAGE_TAG) |
| /health endpoint | ✅ | Liveness check |
| /ready endpoint | ✅ | DB backend reachability check |
| /health/worker | ✅ | Worker queue status |
| /health/db | ✅ | DB connection + migration check |
| /health/browser | ✅ | Browser pool check |
| **Gap** | ⚠️ | No Docker integration test verifying stack starts and survives restart |
| **Gap** | ❌ | No CI job that builds Docker image and runs smoke tests against it |

## Goal 7 — Product Clarity: 74/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| README positioning | ⚠️ | Describes as "pre-production" and "not production-ready" — honest but downplays MVP viability |
| Experimental modules | ✅ | Marked explicitly ("experimental unless a specific test result says otherwise") |
| Docs clarity | ✅ | AGENT_TRUTH.md, MODULE_CLASSIFICATION.md, LIMITATIONS.md |
| **Gap** | ⚠️ | README says "Do not claim this project is a universal scraper" — defensive, not aspirational |
| **Gap** | ⚠️ | No simple "How to scrape a website" quick start in README |

## Goal 8 — Benchmarks: 68/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Benchmark suite exists | ✅ | backend/benchmarks/ with smoke, corpus, anti-bot, longevity, replay |
| Smoke test | ✅ | 33 passed, 2 skipped, 14 local corpus cases, F1=1.0 |
| **Gap** | ⚠️ | Only 14 cases in local corpus — needs 10-20 live/public test pages |
| **Gap** | ⚠️ | No live benchmark run (all local corpus) |
| **Gap** | ⚠️ | No single command to run benchmarks and generate summary |

## Summary Scores

| Domain | Score | Status |
|--------|-------|--------|
| Backend reliability | 85 | ✅ Solid test coverage, exception handling narrowed, mock patterns fixed |
| Frontend | 75 | ⚠️ Build/lint pass but UI is dashboard-centric, not product-path |
| Scraping reliability | 82 | ✅ Job lifecycle APIs complete, URL safety mature |
| Security | 83 | ✅ SSRF, RBAC, API keys, denylist, audit logging |
| Tests | 85 | ✅ 8043+ pass, ruff clean, CI gates passing |
| DevOps | 72 | ⚠️ Docker valid but untested, no CI Docker smoke |
| Docs | 74 | ⚠️ Honest but defensive positioning |
| Product clarity | 68 | ❌ Experimental features dominate UI, no simple scraper flow |
| SaaS readiness | 70 | ⚠️ Core pieces exist but not assembled into one excellent flow |
| Benchmarks | 68 | ⚠️ Infrastructure exists, only local corpus, no live sites |