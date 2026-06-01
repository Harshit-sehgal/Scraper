# Module Classification

**Last refreshed:** 2026-06-01
**Scope:** Major modules/packages, not every helper file
**Observed count:** `151` Python files under `backend/app`

Classification values: Core, Stable supporting, Experimental, Test-only, Deprecated, Candidate for removal, Unknown.

| Module or package | Classification | Purpose | Evidence of use | Tests | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| `app.main` | Core | FastAPI app, middleware, routes, static mounts | API entry point | Safe suite, route matrix | Production routing unvalidated | Keep |
| `app.routers.jobs` | Core | Job lifecycle API | Registered in app | API tests | Auth errors affect core product | Keep |
| `app.routers.exports` | Core | CSV/JSON/Excel exports | Registered in app | Export/API tests | Large export behavior unvalidated | Keep |
| `app.routers.scraper` | Core | Scraper telemetry/config/diagnostics routes | Registered in app | Safe suite, route matrix | Many experimental subroutes | Keep, label experimental endpoints |
| `app.routers.operator` | Stable supporting | Operator dashboard/control routes | Registered in app | Route matrix | Admin/operator exposure risk | Keep |
| `app.scraper` | Core | Scrape orchestration | Used by jobs and tests | Safe/browser tests | Large file and many experimental hooks | Keep, refactor later |
| `app.browser`, `app.browser_pool` | Core | Playwright browser lifecycle | Used by scraper | Browser suite and container Chromium smoke | Broad website behavior unvalidated | Keep |
| `app.extraction_orchestrator` | Core | Schema/selector/network/text fallback extraction | Used by scraper | Safe/browser tests | Accuracy unproven | Keep |
| `app.extractors/*` | Core | Extraction helpers | Imported by orchestrator/tests | Safe suite | Varies by site structure | Keep |
| `app.schema_*`, `app.models` | Core | Job/schema/data models | Broad imports | Safe suite | Contract changes are high-impact | Keep |
| `app.job_store`, `app.storage_interface` | Core | SQLite storage and backend factory | Used by app/tests | Safe suite | Local state artifacts if paths misconfigured | Keep |
| `app.postgres_repository` | Core | Postgres storage backend | Optional tests | Postgres `1885 passed` and Compose smoke/basic dump-restore | Production migrations/failover unvalidated | Keep |
| `app.worker_queue`, `app.worker_queue_postgres` | Core | Local/Postgres queue behavior | Worker scripts/tests | Safe, Postgres, and Compose smoke | Multi-job/failure behavior in target deployment unvalidated | Keep |
| `app.utils.rbac` | Core supporting | API key roles and dependencies | Used by routes/main | Route-auth tests | Dev mode permissive without keys | Keep |
| `app.url_safety` | Core supporting | SSRF-oriented URL checks | Used by scraper/API | Security tests | DNS/egress controls need deployment support | Keep |
| `app.rate_limiter` | Stable supporting | In-memory rate limiting | Middleware/tests | Safe suite | Single-process only | Keep, document limit |
| `app.utils.prod_security_validator` | Stable supporting | Production secret/env checks | Startup/scripts/tests | Prod-security tests | Does not prove runtime security | Keep |
| `app.metrics`, `app.telemetry`, `app.diagnostics` | Stable supporting | Metrics and diagnostics | Main/router imports | Safe suite and local Prometheus scrape | Target exposure/routing unvalidated | Keep |
| `app.audit_logger` | Stable supporting | Audit event logging | Security flows/tests | Safe suite | Log retention/rotation unvalidated | Keep |
| `app.selector_profiles`, `app.selector_memory`, `app.selector_decay` | Experimental | Selector reuse/profile adaptation | Scraper imports/tests | Partial | May be overclaimed as self-learning | Keep isolated |
| `app.strategy_evolution` | Experimental | Strategy recommendation | Scraper imports/tests | Unit plus browser regression | Random exploration can affect extraction path | Keep; cold-start bug fixed |
| `app.semantic_world_state/*` | Experimental | Semantic state model | Imported by system routes/scraper | Mixed | Research-like surface | Keep labeled experimental |
| `app.topology*`, `app.federation*`, `app.gossip*`, `app.vector_clock*` | Experimental | Topology/federation state | System routes/tests | Mixed | Not distributed consensus evidence | Keep labeled experimental |
| `app.replay*`, `app.regression_capture`, `app.chaos*`, `app.failure*` | Experimental/Test-supporting | Replay, diagnostics, failure simulation | Tests and diagnostics | Mixed | Not production self-healing evidence | Keep labeled experimental |
| `app.domain_*`, `app.intent_*`, `app.energy_*`, `app.motif_*`, `app.manifold_*`, `app.instability_*`, `app.acquisition_*` | Experimental | Adaptive/research scoring and state | Scraper/system imports | Mixed | Easy to market inaccurately | Keep internal |
| `backend/tests/*` | Test-only | Automated and manual validation | Pytest/manual | Current results documented | Optional skips can hide gaps | Keep and classify flags |
| `backend/benchmarks/*` | Test-only/Experimental | Smoke and benchmark scaffolding | Pytest/manual | `1 passed` smoke | Not real accuracy proof | Keep, add thresholds |
| `scripts/*` | Stable supporting | Startup, validation, release checks | Manual/CI use | Some tests | Script drift | Keep, validate |
| `frontend/*` | Stable supporting | Static internal dashboard | Static mount | Limited | Hostile-browser/session risk | Keep internal |

## Candidate For Removal

No source module was deleted in this cleanup. Runtime artifacts, caches, local DBs, logs, and locks are removal candidates only when untracked/generated.

## Policy

Experimental code may stay if it is clearly labeled and not used as evidence for production, autonomy, self-healing, distributed consensus, or intelligence claims.
