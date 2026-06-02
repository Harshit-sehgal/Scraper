# Refactoring Plan — Large Experimental Modules

**Date:** 2026-06-02
**Status:** Plan only — not yet implemented

## Motivation

Three experimental modules exceed healthy file sizes (~500+ lines), making them
hard to maintain, test, and reason about. This document outlines a safe,
incremental refactoring strategy that preserves behavior while reducing
cognitive load.

Current sizes (lines of Python, excluding blank lines/comments):

| File | Lines | Primary risk |
|------|-------|-------------|
| `backend/app/topology_state.py` | 1624 | God object: topology state + logic + persistence |
| `backend/app/semantic_segmentation.py` | 1221 | Mixed responsibilities: parsing, scoring, extraction |
| `backend/app/chaos_simulator.py` | 1004 | Simulation logic + reporting + configuration |

---

## 1. `topology_state.py` (1624 lines)

### Current responsibilities
- Region/topology data model definitions
- Region lifecycle management (create, merge, split, prune)
- Topology metrics computation
- Energy/entropy/integrity derived computations
- Persistence serialization/deserialization
- Semantic community detection and clustering

### Proposed split

```
topology_state.py          →  Core data models (~200 lines)
                                 Region, RegionType, TopologyLink
                              + TopologyEngine controller (~300 lines)
                                 Region lifecycle, prune, split, merge
topology_metrics.py         →  Metrics computation (~200 lines)
                                 energy, entropy, convergence, integrity
topology_clustering.py      →  Community detection (~200 lines)
                                 semantic clustering, shard assignment
topology_persistence.py     →  Serialization/deserialization (~100 lines)
                                 to_dict, from_dict, merge
```

### Risk: Medium
- Internal callers import `Region` and various functions from `topology_state`
- Must preserve backward-compatible imports during transition
- Tests exist: 1 test file for topology modules

### Strategy
1. Extract pure data models first (zero behavioral change)
2. Extract metrics next (pure computation, easy to verify)
3. Extract clustering last (more complex, needs integration test)
4. Keep backward-compatible aliases in `topology_state.py` for 1 release cycle

---

## 2. `semantic_segmentation.py` (1221 lines)

### Current responsibilities
- HTML parsing and DOM tree analysis
- Visual block/segment detection
- Content scoring and filtering
- Spatial relationship analysis (proximity, containment)
- Semantic segment extraction

### Proposed split

```
semantic_segmentation.py        →  Core segment model + orchestration (~200 lines)
                                    HtmlSegment, SemanticSegment, orchestrator
dom_segment_parser.py           →  DOM tree parsing and analysis (~300 lines)
                                    DOM walker, node type classification
dom_segment_scorer.py           →  Content quality scoring (~200 lines)
                                    score_segment, filter_noise
dom_segment_spatial.py          →  Spatial relationship analysis (~200 lines)
                                    proximity, containment, layout detection
```

### Risk: Medium-High
- Many internal consumers import from this module
- DOM analysis is inherently complex and hard to test in isolation
- No existing test file for this module

### Strategy
1. Add integration-level tests for the current monolithic module first
2. Extract pure scoring functions (no DOM dependency)
3. Extract spatial analysis helpers
4. Extract DOM parser
5. Keep orchestrator as thin coordinator

---

## 3. `chaos_simulator.py` (1004 lines)

### Current responsibilities
- Failure scenario definitions and configuration
- Chaos experiment lifecycle (start, run, observe, stop)
- Metric collection during experiments
- Report generation
- Integration with failure_injector and domain_intelligence

### Proposed split

```
chaos_simulator.py          →  Core experiment orchestrator (~200 lines)
                                 run_experiment, observe, stop
chaos_scenarios.py          →  Scenario definitions (~300 lines)
                                 network_failure, anti_bot_escalation, ...
chaos_metrics.py            →  Metrics collection and reporting (~200 lines)
                                 collect_metrics, generate_report
```

### Risk: Low
- Primarily used for simulation/testing, not production paths
- Module is relatively self-contained
- Existing test file provides safety net

### Strategy
1. Extract scenario definitions (pure data)
2. Extract metrics/reporting (pure computation)
3. Both can be done without modifying the orchestrator's public API

---

## General Principles

1. **No behavioral changes** — refactoring must preserve exact behavior at
   each step. Use `git diff --stat` and test runs to verify.

2. **Backward-compatible imports** — keep re-exports in original files during
   transition so existing `from app.topology_state import Region` keeps working.

3. **Test before and after** — run existing tests before each extraction,
   confirm they pass, then run after extraction and confirm they still pass.

4. **Incremental PRs** — do not refactor all three files in a single PR.
   Each file should be its own PR, with the PR description referencing this
   plan and noting the specific split.

5. **Priority order**: `topology_state.py` (largest, has test coverage) →
   `chaos_simulator.py` (self-contained, has tests) →
   `semantic_segmentation.py` (complex DOM logic, no existing tests — needs
   test scaffolding first).

## Deferred — Core Product Refactors

The following files are intentionally excluded from the immediate experimental
refactoring plan, but are identified by the deep-research-report.md as
candidates for larger structural refactoring. These are **core product paths**
that require design input before implementation.

| File | Lines | Issue | Effort |
|------|-------|-------|--------|
| `backend/app/main.py` | ~450 | Mixed concerns: app factory, middleware, lifespan, health/readiness, metrics, static mounts, API docs control | Medium |
| `backend/app/scraper.py` | ~800 | Single file handles fetch, orchestration, post-processing, and diagnostics | High |
| `backend/app/services/job_runner.py` | ~600 | `run_job()` monolithic — combines discovery, per-url execution, aggregation, finalization | High |
| `backend/app/extraction_orchestrator.py` | ~500 | Multi-layer extraction cascade is correct but implementation is a monolith | Medium |
| `backend/app/job_store.py` + `postgres_repository.py` | ~1500 combined | SQLite and Postgres persistence duplicate model transforms | High |
| `backend/app/worker_queue.py` + `worker_queue_postgres.py` | ~800 combined | Queue implementations duplicate logic | Medium |

### 4. Rebuild main.py into thin app factory

**Goal:** Separate app creation from middleware/route wiring so individual
components (middleware, routers, lifecycle) can be tested in isolation.

**Proposed structure:**
```
main.py               →  create_app() factory (~50 lines)
                           Import and compose: middleware, routers, lifespan
app/lifespan.py        →  Startup/shutdown lifecycle hooks
app/middleware.py       →  Body size, API key, latency tracking middleware
app/routers/            →  Already mostly separated — just needs cleaner factory wiring
```

**Risk:** Medium — changing import paths affects all tests that import from `app.main`

### 5. Split scraper.py into focused modules

**Goal:** Separate fetch orchestration, extraction orchestration, post-processing,
and diagnostics into their own modules with clear interfaces.

**Proposed structure:**
```
scraper.py              →  Public API: scrape_url(), scrape_url_attempt() (~200 lines)
                              Orchestration logic, result assembly only
extraction/
  fetch.py               →  fetch_page_content(), _fetch_with_httpx(), browser dispatch (~200 lines)
  extraction_orchestrator.py  →  Already exists — use directly
  post_process.py        →  quality scoring, dedup, enrichment (~200 lines)
  diagnostics.py         →  telemetry collection, failure classification (~150 lines)
```

**Risk:** High — scraper.py has the highest complexity in the codebase;
many modules import from it

### 6. Split run_job() into lifecycle phases

**Goal:** Decompose `run_job()` into discovery, per-url scrape, aggregation,
and finalization steps.

**Proposed structure:**
```
services/job_runner.py   →  run_job() orchestrator (~150 lines)
                               Phase 1: discover_urls()
                               Phase 2: scrape_all_urls()
                               Phase 3: aggregate_results()
                               Phase 4: finalize_job()
services/discovery.py    →  URL discovery logic (extracted from job_runner)
services/aggregation.py  →  Result merging, dedup, quality reports
```

**Risk:** High — run_job() is the central hot path; any regression breaks all jobs

### 7. Consolidate repository interfaces

**Goal:** Eliminate SQLite/Postgres duplication behind shared serializers.

**Proposed structure:**
```
persistence/
  repository.py        →  JobRepository ABC (already exists in storage_interface.py)
  serializers.py       →  Shared _job_to_row() / _row_to_job() for both backends
  sqlite.py            →  SQLiteJobRepository (current job_store.py)
  postgres.py          →  PostgresJobRepository (current postgres_repository.py)
  queue.py             →  Shared queue abstractions
```

**Risk:** High — touches every persistence path; tests must run on both SQLite and Postgres

### 8. Separate experimental namespace

**Goal:** Move experimental modules to `experimental/` namespace or behind explicit
feature flags so core versus experimental is obvious in the file tree.

**Candidates:** `semantic_*`, `topology_*`, `gossip_*`, `federation_*`,
`manifold_*`, `intent_*`, `energy_*`, `motif_*`, `chaos_*`, `insight_engine.py`

**Strategy:**
1. Create `backend/app/experimental/` directory
2. Move modules one at a time, keeping backward-compatible imports
3. Gate experimental routes behind `ENABLE_EXPERIMENTAL_ROUTES` (already exists)

**Risk:** Medium — many imports reference these modules; needs careful aliasing

---

### Refactoring Priority (All Items)

| Priority | Module | Effort | Dependencies |
|----------|--------|--------|-------------|
| 1 | `topology_state.py` → 3 extracted modules | Medium | Has test coverage |
| 2 | `chaos_simulator.py` → 2 extracted modules | Low | Self-contained |
| 3 | `main.py` → app factory | Medium | No behavioral changes |
| 4 | `run_job()` → lifecycle phases | High | Requires scraper.py split first |
| 5 | `scraper.py` → focused modules | High | Largest module, most complex |
| 6 | Repo consolidation (SQLite/Postgres) | High | Depends on stable API contracts |
| 7 | `semantic_segmentation.py` → 3 extracted modules | Medium-High | Needs tests first |
| 8 | Experimental namespace move | Medium | Depends on feature flag decisions |

### General Principles

1. **No behavioral changes** — refactoring must preserve exact behavior at
   each step. Use `git diff --stat` and test runs to verify.

2. **Backward-compatible imports** — keep re-exports in original files during
   transition so existing imports keep working.

3. **Test before and after** — run existing tests before each extraction,
   confirm they pass, then run after extraction and confirm they still pass.

4. **Incremental PRs** — each module is its own PR referencing this plan.

5. **Dependency order matters** — don't split scraper.py until run_job()
   phases are stable, and don't consolidate repos until model contracts are frozen.
