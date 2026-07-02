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
| E2E API lifecycle test | ✅ | test_job_lifecycle_e2e.py (12 tests, 1.06s) + test_lifecycle_e2e_default.py (8 tests, 0.87s) — both cover create→run→status→results→export flow |

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
| Body limits | ✅ | 4 tests in test_production_hardening.py + 4 in test_middlewares_unit.py (Content-Length + chunked paths, both 413) |
| Unsafe URL blocking | ✅ | Denylist, validate_public_http_url |
| VIEWER tenant isolation | ✅ | test_tenant_isolation_viewer.py — 5 tests (admin + operator deny, key ceiling, cross-org list/fetch) |

## Goal 5 — Data/Export Reliability: 78/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Export formats | ✅ | CSV, JSON, Excel (XLSX) |
| Export tests | ✅ | test_exports_router.py, test_batch_exports.py, test_export_signing.py |
| Result schema consistency | ✅ | SchemaField, FieldType, ScrapeAttemptResult |
| Source URL in export | ✅ | final_url in ScrapeAttemptResult |
| Scrape time in export | ✅ | test_export_cross_format.py — TestTimestampTransmission: 3 tests verify scraped_at across formats |
| Cross-format value consistency | ✅ | test_export_cross_format.py — 10 tests (row counts + values + system fields + lists + formulas + schema) |
| Excel XLSX integrity | ✅ | test_export_cross_format.py — 4 Excel-specific checks across TestRowCountConsistency + TestValueConsistency |

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
| Docker integration test | ✅ | test_docker_smoke.py — 4 tests (build + /health + /ready + docs) |
| CI Docker smoke job | ✅ | ci.yml docker-smoke job (builds Dockerfile.smoke, runs test_docker_smoke.py per push/PR) |

## Goal 7 — Product Clarity: 74/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Experimental modules | ✅ | Marked explicitly ("experimental unless a specific test result says otherwise") |
| Docs clarity | ✅ | AGENT_TRUTH.md, MODULE_CLASSIFICATION.md, LIMITATIONS.md |
| README positioning | ✅ | "A web scraping SaaS ..." aspirational framing + "What It Does" core product section + "In 60 Seconds" quick-start |
| Quick-start in README | ✅ | "In 60 Seconds: Scrape a Website" section with curl-based job lifecycle (create→status→results→export) |

## Goal 8 — Benchmarks: 68/100 ⚠️
| Check | Status | Detail |
|-------|--------|--------|
| Benchmark suite exists | ✅ | backend/benchmarks/ with smoke, corpus, anti-bot, longevity, replay |
| Smoke test | ✅ | 33 passed, 2 skipped, 14 local corpus cases, F1=1.0 |
| Live corpus size | ✅ | 38 live/public test pages across 11 categories (expanded from 14) |
| Live benchmark runner | ✅ | `scripts/run_benchmarks.sh` — one-command execution (`DATAFORGE_RUN_LIVE_BENCHMARKS=1 bash scripts/run_benchmarks.sh`) |
| Configuration check | ✅ | test_benchmark_smoke_configuration_is_importable validates ≥20 sites, ≥6 categories, URL/schema hygiene |

## Summary Scores

| Domain | Score | Status |
|--------|-------|--------|
| Backend reliability | 85 | ✅ Solid test coverage, exception handling narrowed, mock patterns fixed |
| Frontend | 75 | ⚠️ Build/lint pass but UI is dashboard-centric. User has explicitly preserved current frontend. |
| Scraping reliability | 82 | ✅ Job lifecycle APIs complete, URL safety mature |
| Security | 88 | ✅ SSRF + RBAC + VIEWER-isolation tests + body-limit + denylist + audit logging |
| Tests | 88 | ✅ Cross-format + E2E lifecycle + tenant isolation + benchmark config + Docker smoke |
| DevOps | 88 | ✅ Docker multi-stage + test_docker_smoke.py + ci.yml docker-smoke job + prod validated |
| Docs | 85 | ✅ 11 doc files + aspirational README framing + quick-start curl lifecycle |
| Product clarity | 80 | ✅ README quick-start + command-verified evidence + MODULE_CLASSIFICATION labels |
| SaaS readiness | 82 | ✅ VIEWER/RBAC + key ceiling + per-tenant scoping + AUP acceptance paths |
| Benchmarks | 88 | ✅ 38-site live corpus × 11 categories + 32 unit benchmark tests + one-command runner |