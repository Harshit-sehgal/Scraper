# Module Classification — Architecture Reality Map

**Classification:** Architectural Reality Map & Integrity Review  
**Date:** 2026-05-31

This document is a working architecture map for the 151 Python modules in `backend/app`. It separates core implementation areas from optional and experimental components. It is not a complete proof that every listed module is production-ready.

---

## 1. Architectural Layers & Classification Schema

We classify all modules into one of the following 10 architectural layers:

*   **Core (Layers 1-4, 6-8):** Essential for a practical, configurable web extraction system. High reliability and comprehensive test coverage are required.
*   **Optional/Enrichment (Layer 5, 9):** Enhances the system (e.g. LLM extraction, UI) but is not required for core operations.
*   **Experimental (Layer 10):** Aspirational, research-oriented modules (e.g. topology states, evolutionary strategies). These are **not** production-ready features.

---

## 2. Comprehensive Module Classification Table

| File / Module | Layer | Purpose | Used By | Test Coverage | Maturity | Action | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `app/main.py` | **Layer 1 — API Layer** | FastAPI application entry point & startup/shutdown lifespans | HTTP Clients / Frontend | High (`test_api_regressions.py`) | **Verified** | **Keep** | Central orchestrator. Runs production startup env checks when active. |
| `app/routers/` | **Layer 1 — API Layer** | Exposes REST endpoints (`/api/jobs`, `/api/scraper`, `/api/exports`, etc.) | Frontend Dashboard | High (`test_storage_endpoints.py`, `test_exports_router.py`) | **Verified** | **Keep** | Enforces routing, input model validation, and basic response mappings. |
| `app/config.py` | **Layer 1 — API Layer** | Configuration source of truth and Pydantic Settings management | Entire Application | High (`test_deterministic_dotenv.py`) | **Verified** | **Keep** | Loads configurations. Production env gates reject weak/placeholder credentials. |
| `app/worker_queue.py` | **Layer 2 — Job Layer** | Orchestrates worker loops and in-memory priority execution | Job Runner / API Routers | High (`test_worker_queue.py`) | **Verified** | **Keep** | Handles job retry thresholds, DLQs, and worker dispatching. |
| `app/services/job_runner.py`| **Layer 2 — Job Layer** | Background worker thread management and job extraction trigger | worker_queue.py | High (`test_job_lifecycle.py`) | **Verified** | **Keep** | Executes background scrape jobs and updates the persistent storage layers. |
| `app/browser_pool.py` | **Layer 3 — Scraping Layer** | Manages Playwright browser instances and Chromium rendering contexts | app/scraper.py | Medium (`test_playwright_browser_e2e.py`) | **Verified** | **Keep** | Prevents browser leakages. Handles user-agents and browser parameters. |
| `app/browser_network_capture.py` | **Layer 3 — Scraping Layer** | Captures network payloads, headers, and media sizes during rendering | app/scraper.py | Medium (`test_browser_network_capture.py`) | **Verified** | **Keep** | Essential for profiling Javascript-heavy web extraction targets. |
| `app/rendered_visible_text_extractor.py` | **Layer 3 — Scraping Layer** | Extracts raw text from page rendering nodes after JS settles | app/scraper.py | Medium | **Verified** | **Keep** | Useful for DOM content matching without selector knowledge. |
| `app/scraper.py` | **Layer 4 — Extraction Layer** | Playwright page loader, robots.txt reader, HTML fetcher, rate-respecter | Job Runner | High (`test_playwright_browser_e2e.py`) | **Verified** | **Keep** | Connects Layer 3 (Browser rendering) with Layer 4 (Structured selectors). |
| `app/extraction_orchestrator.py` | **Layer 4 — Extraction Layer** | Runs CSS/XPath selector matching and orchestrates fallback rules | app/scraper.py | High (`test_selector_discovery.py`) | **Verified** | **Keep** | Resolves CSS path rules, validates fields, and records data provenance. |
| `app/field_validator.py` | **Layer 4 — Extraction Layer** | Validates structured data fields against standard Pydantic Schema | Extraction Orchestrator | High (`test_field_validator.py`) | **Verified** | **Keep** | Supports validation patterns (e.g. emails, numeric ranges, non-empty). |
| `app/empty_response_detector.py`| **Layer 4 — Extraction Layer** | Classifies empty HTTP results into captcha, cookie walls, JS shell, etc. | zero_result_classifier.py | High (`test_empty_response_detector.py`) | **Verified locally** | **Keep** | Regex spacing issue corrected; covered by local tests. |
| `app/zero_result_classifier.py` | **Layer 4 — Extraction Layer** | Resolves high-level extraction failure categorization | app/scraper.py | High (`test_zero_result_classifier.py`) | **Verified** | **Keep** | Gives detailed diagnostics about why scraping produced zero-length results. |
| `app/llm_bridge.py` | **Layer 5 — Enrichment Layer** | Bridges LLM clients (Groq) for optional semantic cleaning | Extraction Orchestrator | Medium (`test_llm_bridge.py`) | **Partially Verified** | **Keep (Optional)** | Skips tests globally when GROQ_API_KEY is not defined. Uses timing-safe falls. |
| `app/llm_validator.py` | **Layer 5 — Enrichment Layer** | Employs optional LLM verification of parsed selector fields | Extraction Orchestrator | Medium (`test_llm_validator.py`) | **Partially Verified** | **Keep (Optional)** | Secondary semantic helper; not required for core operations. |
| `app/state_store.py` | **Layer 6 — Storage Layer** | Flat-file SQLite JSON backup state storage and flushing triggers | API Routers | High (`test_state_store.py`) | **Verified** | **Keep** | Backup storage. Handles thread-safe atomic file flushes on termination. |
| `app/postgres_repository.py` | **Layer 6 — Storage Layer** | PostgreSQL database connectivity, pools, and SQL schema builders | worker_queue_postgres.py | High (`test_postgres_repository.py`) | **Partially Verified** | **Keep** | Code exists and is unit-tested, but requires running local Postgres DB. |
| `app/job_store.py` | **Layer 6 — Storage Layer** | Main in-memory / SQLite-backed CRUD operations for Job statuses | API Routers | High (`test_job_store_persistence.py`) | **Verified** | **Keep** | Main persistence interface. Stable, thread-safe. |
| `app/observability.py` | **Layer 7 — Telemetry** | Telemetry collectors, system resource loggers, performance probes | Entire Application | High (`test_metrics.py`) | **Verified** | **Keep** | Exposes Prometheus counters `/metrics`. Blocked by nginx externally. |
| `app/rate_limiter.py` | **Layer 8 — Security Layer** | Timing-safe in-memory sliding-window request rate limiter | API Middleware | High | **Verified** | **Keep** | Single-process only. For distributed multi-process, needs Redis-level WAF. |
| `app/url_safety.py` | **Layer 8 — Security Layer** | Timing-safe SSRF defense blocking loopback, private IPs, cloud metadata | app/scraper.py | High (`test_url_safety.py`) | **Verified** | **Keep** | Prevents internal network scanning. Crucial security barrier. |
| `app/audit_logger.py` | **Layer 8 — Security Layer** | High-security rotating system audit log (captures auth fails, non-GETs) | API Key Middleware | High (`test_audit_logger.py`) | **Verified** | **Keep** | Writes to `logs/audit.log` (now ignored in git, correctly rotated). |
| `frontend/` | **Layer 9 — Dashboard Layer** | Internal client-side dashboard with API key config storage | End User Browser | None | **Partially Verified** | **Keep (Internal Only)**| Store API keys in localStorage (XSS risk). Must not be exposed publicly. |
| `app/topology_state.py` | **Layer 10 — Experimental** | Highly complex CRDT graph structure for "cognitive self-healing" | Optional Pipelines | Weak (`test_topological_query.py`) | **Experimental** | **Mark Experimental**| Aspirational CRDT logic. Not recommended for production workflows. |
| `app/manifold_state.py` | **Layer 10 — Experimental** | Metric vector manifold alignment and "world state" persistence | Optional Pipelines | Weak | **Experimental** | **Mark Experimental**| High mathematical drift risk. Unused by core scraping pipelines. |
| `app/chaos_simulator.py` | **Layer 10 — Experimental** | Simulates failure injection, split-brain desyncs, network drops | Test fixtures | Weak (`test_chaos_engineering.py`) | **Experimental** | **Mark Experimental**| Test-only failure injector. Must be kept disabled in production envs. |
| `app/strategy_evolution.py` | **Layer 10 — Experimental** | Genetic/evolutionary optimizer matching selector weights over time | Optional Pipelines | Weak (`test_strategy_evolution.py`) | **Experimental** | **Mark Experimental**| Research code. Accuracy and convergence properties are unproven. |

---

## 3. Core vs. Experimental Separation Policy

To preserve the maintainability and integrity of DataForge Scraper, future contributors must enforce these boundaries:

1.  **Core Isolation:** Essential components (Layers 1-4, 6-8) should avoid depending on Layer 10 (Experimental) modules. If a dependency exists, it must be documented and tested.
2.  **No Magic Terminology in Core:** Core modules must use standard engineering terms (e.g. `retries`, `fallbacks`, `selector matching`) instead of hype buzzwords (`cognitive steering`, `world-state harmony`, `metamorphic healing`).
3.  **Strict Security Barriers:** All operations under Layer 8 (SSRF, URL validation, timing-safe key validation, role access control) are **absolute production gates** that must never be bypassed or weakened to make tests pass.
