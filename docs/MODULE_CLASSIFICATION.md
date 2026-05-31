# Module Classification — DataForge Scraper

> **Current as of:** 2026-05-31
> **This is a living document.** Update as modules are added, removed, or migrated between layers.

## Classification Legend

| Column | Meaning |
|---|---|
| **Layer** | Architectural layer the module belongs to |
| **Module** | File path under `backend/app/` |
| **Purpose** | What the module does |
| **Depends on** | Key modules it imports from |
| **Test file(s)** | Corresponding test files (if any) |
| **Test coverage** | Estimated coverage quality |
| **Maturity** | `core` = production-adjacent, `stable` = well-tested, `experimental` = unvalidated, `legacy` = needs review |
| **Recommendation** | keep / refactor / archive / delete |

## Layer 1 — API Layer

FastAPI app, routers, middleware, health, readiness, metrics.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `main.py` | FastAPI app creation, lifespan, middleware (CORS, auth, body size, rate limit, latency tracking), route definitions, metrics endpoint, static file serving | routers, config, metrics_collector, audit_logger, rate_limiter, state_store, storage_interface | `test_scaling.py` (partial) | Low — integration tests exist but no direct main.py fixture | **core** | keep |
| `routers/jobs.py` | Job CRUD router: create, list, get, cancel, delete, recycle bin, search, results, config | models, job_store, services.job_runner | `test_exports_router.py`, `test_operator.py` (indirect) | Medium — route tests exist | **core** | keep |
| `routers/exports.py` | Export router: CSV, JSON, Excel exports | models, utils.export, utils.job_results_store | `test_exports_router.py` | Medium | **core** | keep |
| `routers/scraper.py` | Scraper config/telemetry router | annotation_models (likely in models.py) | — | Low | **core** | keep |
| `routers/operator.py` | Operator/admin routes: mode switching, health monitoring | models, config | `test_operator.py` | Medium | **core** | keep |

## Layer 2 — Job Layer

Job creation, persistence, lifecycle, queueing, cancellation, recycling, results.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `services/job_runner.py` | Core job execution logic: discovery, fetch, process, persist | scraper, extraction_orchestrator, storage_interface, models, utils.job | `test_job_lifecycle.py` | Medium — lifecycle tests exist | **core** | keep |
| `services/state.py` | State persistence functions for job lifecycle | storage_interface | — | Low | **core** | keep |
| `job_store.py` | Job state persistence (SQLite): schema migrations, CRUD | — | `test_atomic_repository_ops.py`, `test_semantic_persistence.py` | Medium | **core** | keep |
| `worker_queue.py` | In-process/SQLite worker queue: priority, retries, dead-letter | — | `test_scaling.py` | Medium | **core** | keep |
| `worker_queue_postgres.py` | PostgreSQL-backed worker queue | postgres_repository | — | Low | **stable** | keep |
| `utils/job.py` | Job utilities: result normalization, dedup, cancellation | models | — | Low | **core** | keep |
| `utils/job_results_store.py` | Disk-based result storage with compression/pagination | — | — | None | **stable** | keep |
| `utils/export.py` | Export format generation (CSV, JSON, Excel) | models | — | Low | **core** | keep |
| `crawl_frontier.py` | URL frontier management for crawl jobs | crawl_policy | — | None | **experimental** | refactor |
| `crawl_policy.py` | Crawl policy: rate limits, politeness | — | — | None | **experimental** | refactor |
| `crawl_state.py` | Crawl state adapter for frontier/policy | crawl_frontier, crawl_policy | — | None | **experimental** | refactor |

## Layer 3 — Scraping Layer

Browser loading, HTML fetching, Playwright, network capture, visible text, page profiling.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `scraper.py` | High-level scrape orchestrator: fetch, extract, telemetry, error classification | browser_pool, extraction_orchestrator, scrape_telemetry, html_utils, url_safety | — | Low | **core** | keep |
| `browser_pool.py` | Playwright browser instance pool management | — | — | Low | **stable** | keep |
| `html_utils.py` | HTML fetching utilities (httpx/Playwright) | — | — | Low | **core** | keep |
| `network_extractor.py` | Extract structured records from network JSON payloads | — | `test_network_payload_extractor.py` | Medium | **stable** | keep |
| `network_payload_extractor.py` | Find structured records in captured network JSON | — | — | Low | **stable** | keep |
| `browser_network_capture.py` | Capture XHR/fetch responses during page load | — | — | Low | **stable** | keep |
| `rendered_visible_text_extractor.py` | Extract from visible text blocks when selectors fail | — | — | Low | **stable** | keep |
| `page_profiler.py` | Page structure detection (table/cards/list/key-value) | — | — | Low | **stable** | keep |
| `page_evidence_collector.py` | Gather evidence from rendered page for extraction | — | — | None | **experimental** | refactor |
| `empty_response_detector.py` | Detect empty/blocked page responses | — | — | None | **stable** | keep |
| `session_url_detector.py` | Detect ephemeral URL params, generate canonical URLs | — | — | None | **stable** | keep |
| `snapshot_desync_detector.py` | Detect desync between browser and network state | — | — | None | **experimental** | refactor |

## Layer 4 — Extraction Layer

Selectors, schema fields, field validation, orchestrated extraction, fallback strategies.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `extraction_orchestrator.py` | Cascade of extraction methods: network, selectors, LLM, containers, visible text, regex | selector_engine, network_extractor, container_discovery, rendered_visible_text_extractor, selector_discovery | — | Low | **core** | keep |
| `selector_engine.py` | CSS selector application with fallbacks, schema alignment | — | — | Low | **core** | keep |
| `selector_discovery.py` | LLM-guided CSS selector generation | llm_bridge | — | Low | **stable** | keep |
| `selector_discovery_analysis.py` | Analysis of selector discovery results | selector_discovery | — | Low | **stable** | keep |
| `selector_discovery_url.py` | URL-based selector discovery | selector_discovery | — | Low | **stable** | keep |
| `selector_memory.py` | Domain-selector memory cache with confidence scoring | — | `test_self_tuning_extraction.py` (indirect) | Low | **stable** | keep |
| `selector_ml_optimizer.py` | ML-based selector optimization | selector_memory | — | None | **experimental** | refactor |
| `selector_decay_predictor.py` | Predict selector decay over time | selector_memory | — | None | **experimental** | refactor |
| `container_discovery.py` | Discover data containers in rendered page | — | — | Low | **stable** | keep |
| `self_tuning_extraction.py` | Adaptive extraction parameter tuning | — | `test_self_tuning_extraction.py` | Low | **experimental** | refactor |
| `compound_record_assembler.py` | Assemble compound records from multiple extraction passes | — | — | None | **experimental** | refactor |
| `models.py` | Pydantic models: Job, SchemaField, JobStatus, etc. | — | Many tests | High | **core** | keep |
| `core_types.py` | Core type definitions | — | — | None | **core** | keep |
| `field_validator.py` | Extract field validation (type, format, range) | models | — | Medium | **core** | keep |
| `field_laws.py` | Field law definitions (exclusivity, compatibility constraints) | — | — | None | **experimental** | archive |

## Layer 5 — Cleaning and Enrichment Layer

Data cleaning, LLM-assisted cleaning, schema suggestion, insight generation.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `cleaning_engine.py` | Data cleaning: dedup, normalization, type coercion | — | — | Low | **stable** | keep |
| `llm_bridge.py` | LLM provider abstraction (Groq API) | config | `test_llm_bridge.py` | Low | **stable** | keep |
| `llm_validator.py` | LLM-based extraction validation | llm_bridge | — | None | **experimental** | refactor |
| `insight_engine.py` | Generate insights from extracted data | llm_bridge | `test_insight_engine.py` | Low | **stable** | keep |
| `semantic_mapper.py` | Map extracted values to user intent semantically | — | `test_semantic_mapper.py` | Medium | **experimental** | refactor |
| `intent_parser.py` | Parse user intent from natural language | — | `test_intent_parser_alignment.py` | Low | **experimental** | refactor |

## Layer 6 — Storage Layer

SQLite, Postgres, repositories, state store, result store.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `storage_interface.py` | Abstract JobRepository interface | — | — | High (interface) | **core** | keep |
| `postgres_repository.py` | PostgreSQL JobRepository implementation | storage_interface, config | `test_sharded_federation.py`, `test_scaling.py` | Medium | **stable** | keep |
| `state_store.py` | File-based state persistence (JSON on disk) | — | — | Low | **core** | keep |
| `checkpoint_manager.py` | World state checkpoint creation/loading | — | — | Low | **experimental** | refactor |
| `geocode_cache.py` | Geocode cache for location data | — | — | None | **stable** | keep |

## Layer 7 — Telemetry and Diagnostics

Scrape telemetry, metrics, failure classification, provenance, diagnostics.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `scrape_telemetry.py` | Per-URL scrape telemetry collection | anti_bot_engine | — | Low | **core** | keep |
| `telemetry_state.py` | Adapter for scrape telemetry state management | scrape_telemetry | — | Low | **stable** | keep |
| `metrics_collector.py` | Shared runtime metric counters (latency, failures, errors) | — | `test_metrics.py` | Medium | **core** | keep |
| `scraper_diagnostics.py` | Deep diagnostic scraper introspection | scraper, html_utils, scrape_telemetry, selector_memory, extraction_orchestrator | — | None | **stable** | keep |
| `failure_classification.py` | Classify scrape failures into categories | — | `test_zero_result_classifier.py` (indirect) | Low | **core** | keep |
| `zero_result_classifier.py` | Classify zero-result outcomes | — | — | Medium | **stable** | keep |
| `extraction_provenance.py` | Track extraction source (which method produced each field) | — | — | None | **stable** | keep |
| `degradation_predictor.py` | Predict extraction degradation over time | — | `test_degradation_predictor.py` | Low | **experimental** | refactor |
| `benchmark_reporter.py` | Benchmark result reporting utilities | — | — | None | **experimental** | refactor |
| `benchmark_accuracy.py` | F1 accuracy measurement for benchmark results | — | — | None | **experimental** | refactor |
| `trend_analyzer.py` | Trend analysis for scraping quality | — | — | None | **experimental** | refactor |

## Layer 8 — Security Layer

API key auth, RBAC, SSRF checks, CORS, CSP, rate limiting, audit logging.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `url_safety.py` | URL validation: SSRF prevention, public HTTP URL check | — | `test_url_safety.py` | Medium | **core** | keep |
| `rate_limiter.py` | In-memory request rate limiting middleware | — | — | Low | **core** | keep |
| `utils/rbac.py` | Role-based access control dependencies | — | — | Low | **core** | keep |
| `utils/prod_security_validator.py` | Production credential validation | config | `test_check_prod_env.py` | Medium | **core** | keep |
| `utils/rate_limit.py` | External rate-limit detection utilities | — | — | Low | **stable** | keep |
| `audit_logger.py` | Structured security audit logging | — | `test_check_prod_env.py` (indirect) | Low | **core** | keep |
| `anti_bot_engine.py` | Anti-bot detection and evasion strategies | — | — | Low | **stable** | keep |
| `proxy_manager.py` | Proxy rotation manager | — | — | None | **experimental** | refactor |
| `domain_runtime_policy.py` | Per-domain concurrency/cooldown/failure policies | — | — | Low | **stable** | keep |

## Layer 9 — Dashboard Layer

Static frontend, internal dashboard, polling-based UI.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| *(none in backend/app)* | Frontend is static HTML/CSS/JS in `frontend/` | — | — | None | **stable** | keep |

## Layer 10 — Experimental Layer

Semantic world state, topology, federation, cognitive scheduling, self-tuning, strategy evolution, selector memory, replay, chaos simulation.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `semantic_world_state/` (package, 7 files) | Semantic cognition core: world state, topology, memory, serialization, locks, events, metrics | many internal modules | `test_semantic_persistence.py` | Low | **experimental** | keep (clearly labelled) |
| `semantic_os.py` | Semantic operating system orchestration | semantic_world_state | — | None | **experimental** | keep |
| `semantic_pipeline.py` | Semantic processing pipeline (segmentation → allocation → validation) | — | — | Low | **experimental** | keep |
| `semantic_segmentation.py` | Semantic segmentation of page content | — | — | None | **experimental** | keep |
| `semantic_inference_engine.py` | Semantic inference from extracted data | — | — | None | **experimental** | keep |
| `semantic_boundary_engine.py` | Merge/split decisions for semantic tokens | — | — | None | **experimental** | keep |
| `semantic_allocation_engine.py` | Allocate semantic tokens to regions | — | — | None | **experimental** | keep |
| `semantic_ir.py` | Semantic intermediate representation | — | — | None | **experimental** | keep |
| `semantic_persistence.py` | Persist/restore semantic state | — | `test_semantic_persistence.py` | Low | **experimental** | keep |
| `semantic_events.py` | Event definitions for semantic state changes | — | — | None | **experimental** | keep |
| `topology_state.py` | Topology state: regions, edges, stability | — | — | Low | **experimental** | keep |
| `topology_state_types.py` | Topology type definitions | — | — | Low | **experimental** | keep |
| `topology_view.py` | Read-only view of topology state | — | — | None | **experimental** | keep |
| `topology_api.py` | API for topology mutations | — | — | Low | **experimental** | keep |
| `topology_gc.py` | Garbage collection for topology | — | — | None | **experimental** | keep |
| `topological_query.py` | Topological query/search on knowledge graph | — | — | None | **experimental** | keep |
| `federation_manager.py` | Multi-node consensus and state sync | — | `test_sharded_federation.py` | Low | **experimental** | keep |
| `gossip_substrate.py` | Gossip protocol for distributed state propagation | heartbeat_manager | — | Low | **experimental** | keep |
| `manifold_state.py` | Core state management for semantic manifold | — | — | Low | **experimental** | keep |
| `motif_state.py` | Motif pattern state management | — | — | Low | **experimental** | keep |
| `motif_feedback.py` | Feedback loops for motif reinforcement | — | — | None | **experimental** | keep |
| `abstraction_state.py` | Abstraction hierarchy state management | — | — | None | **experimental** | keep |
| `action_state.py` | Action state: pending/completed actions | — | — | None | **experimental** | keep |
| `acquisition_mode.py` | URL acquisition mode definitions | — | — | None | **experimental** | keep |
| `acquisition_state.py` | Acquisition state machine | — | — | Low | **experimental** | keep |
| `acquisition_telemetry.py` | Acquisition telemetry collection | acquisition_state | — | Low | **experimental** | keep |
| `energy_state.py` | Energy state for cognitive scheduling | — | — | Low | **experimental** | keep |
| `energy_api.py` | API for energy state mutations | — | — | Low | **experimental** | keep |
| `intent_state.py` | Intent state tracking | — | — | None | **experimental** | keep |
| `history_state.py` | Historical state tracking | — | — | Low | **experimental** | keep |
| `instability_state.py` | Instability and immunity state | — | — | None | **experimental** | keep |
| `instability_api.py` | API for instability/immunity management | — | — | Low | **experimental** | keep |
| `transition_state.py` | State transition management | — | — | None | **experimental** | keep |
| `persistence_state.py` | Persistence state management | — | — | None | **experimental** | keep |
| `regression_state.py` | Regression tracking state | — | — | None | **experimental** | keep |
| `regression_capture.py` | Regression capture for data quality | — | `test_regression_capture.py` | Low | **experimental** | keep |
| `transaction_context.py` | Transaction context for atomic state mutations | — | `test_transaction_context.py` | Medium | **experimental** | keep |
| `vector_clock.py` | Vector clocks for distributed causality | — | — | Low | **experimental** | keep |
| `domain_evolution_model.py` | Domain structure evolution modeling | — | — | Low | **experimental** | keep |
| `domain_intelligence.py` | Domain-specific intelligence accumulation | — | — | Low | **experimental** | keep |
| `strategy_evolution.py` | Strategy evolution for extraction approach | — | `test_strategy_evolution.py` | Low | **experimental** | keep |
| `replay_buffer.py` | Large-scale persistent replay buffer | — | — | Low | **experimental** | keep |
| `chaos_simulator.py` | Chaos simulation for failure testing | — | — | Low | **experimental** | keep |
| `failure_injector.py` | Failure injection for testing | — | — | None | **experimental** | keep |
| `recovery_strategies.py` | Recovery strategy definitions | — | — | None | **experimental** | keep |
| `recovery_handlers.py` | Recovery handler registration | — | — | None | **experimental** | keep |
| `scraper_recovery_integration.py` | Integration between scraper and recovery framework | — | — | None | **experimental** | keep |
| `resource_governor.py` | Resource governance for cognitive scheduling | — | — | None | **experimental** | keep |
| `runtime_budget.py` | Runtime budget management | — | — | None | **experimental** | keep |
| `observability.py` | Cognitive observability: telemetry, heatmaps, drift analysis | transaction_context, semantic_world_state | — | Low | **experimental** | keep |
| `event_dispatcher.py` | Event dispatch for semantic state changes | — | — | None | **experimental** | keep |
| `event_journal.py` | Event journal: mutation tracing and causality | replay_buffer | — | Low | **experimental** | keep |
| `graph_update_scheduler.py` | Cognitive task scheduling | — | — | None | **experimental** | keep |
| `heartbeat_manager.py` | Distributed heartbeat/health monitoring | — | — | Low | **experimental** | keep |
| `domain_health_alerts.py` | Domain health degradation alerts | — | — | None | **experimental** | keep |
| `invariant_firewall.py` | Field invariant enforcement around state mutations | — | — | None | **experimental** | keep |
| `policy_engine.py` | Policy engine for extraction behavior | — | — | None | **experimental** | keep |
| `visualization.py` | Topology/state visualization utilities | — | — | None | **experimental** | keep |

## Layer 11 — Supporting / Utility Modules

Cross-cutting utilities not specific to any layer.

| Module | Purpose | Depends on | Test file(s) | Coverage | Maturity | Rec |
|---|---|---|---|---|---|---|
| `config.py` | Centralized pydantic-settings configuration (684 lines) | — | Many tests (environment setup) | Medium | **core** | keep |
| `async_utils.py` | Async utility functions | — | — | Low | **core** | keep |
| `data_utils.py` | Data processing utilities | — | — | Low | **stable** | keep |
| `filters.py` | Filtering utilities for job/results | — | — | None | **stable** | keep |
| `utils/env.py` | Environment variable utilities | — | — | Low | **core** | keep |
| `utils/quality.py` | Quality scoring utilities | — | — | Low | **stable** | keep |
| `__init__.py` | Package init, dotenv loading | — | — | — | **core** | keep |
| `selector_profiles/` (package, 2 files) | Selector profile loading | — | — | Low | **stable** | keep |

## Summary Counts

| Layer | Core | Stable | Experimental | Total |
|---|---|---|---|---|
| 1 — API Layer | 5 | — | — | 5 |
| 2 — Job Layer | 6 | 2 | 3 | 11 |
| 3 — Scraping Layer | 3 | 6 | 2 | 11 |
| 4 — Extraction Layer | 4 | 5 | 3 | 12 |
| 5 — Cleaning/Enrichment | — | 4 | 2 | 6 |
| 6 — Storage Layer | 3 | 2 | — | 5 |
| 7 — Telemetry/Diagnostics | 4 | 3 | 3 | 10 |
| 8 — Security Layer | 6 | 2 | 1 | 9 |
| 9 — Dashboard Layer | — | 1 | — | 1 |
| 10 — Experimental Layer | — | — | 51 | 51 |
| 11 — Supporting/Utility | 3 | 3 | — | 6 |
| **Total** | **34** | **28** | **65** | **127** |

## Key Observations

1. **Experimental modules dominate** — 51 of 127 modules (40%) are experimental semantic/cognitive/topology modules. This is the largest single category.

2. **Core modules are 27%** — 34 modules classified as core. These are the backbone of the platform.

3. **Experimental layer has low test coverage** — Most experimental modules have little to no dedicated test coverage. They are implemented but unvalidated.

4. **No modules recommended for deletion** — All modules have a purpose, even if experimental. The recommendation is to keep experimental modules clearly labelled rather than delete them.

5. **Refactoring candidates** — A few modules in experimental layers could be refactored into core if they prove their value (e.g., `selector_memory` → core, `anti_bot_engine` → core).

6. **Architecture is lawfully verified** — The architecture validator confirms all modules are lawfully connected.

## Archive Candidates

The following modules have unclear utility and could be archived if not actively used:

| Module | Reason |
|---|---|
| `field_laws.py` | Defines static exclusivity/compatibility rules; not referenced by active extraction code |
| `snapshot_desync_detector.py` | No active consumers identified |
| `page_evidence_collector.py` | Overlaps with `page_profiler.py` functionality |
| `selector_profiles/` | May be legacy; verify if referenced by extraction code |
