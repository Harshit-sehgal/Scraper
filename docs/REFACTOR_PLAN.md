# Refactoring Plan — Large Experimental Modules

**Date:** 2026-06-08
**Status:** Phase C — Workers & System Observability (complete); main.py app factory refactored (complete); Research Shell Boundary enforced (complete). Phase 1 (topology_state.py) partially complete.

## Motivation

Two experimental modules exceed healthy file sizes (~500+ lines), making them
hard to maintain, test, and reason about. (`chaos_simulator.py` has already been
extracted.) This document outlines a safe, incremental refactoring strategy
that preserves behavior while reducing cognitive load.

Current sizes (lines of Python, excluding blank lines/comments):

| File | Lines | Primary risk |
|------|-------|-------------|
| `backend/app/topology_state.py` | ~~1624~~ **885** | God object: topology state + logic + persistence |
| `backend/app/semantic_segmentation.py` | 1210 | Mixed responsibilities: parsing, scoring, extraction |
| `backend/app/chaos_simulator.py` | ~~1004~~ **178** | ✅ Extracted — orchestrator only (scenarios/metrics separated) |

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

### Progress

| Extraction | Status | Lines moved | Module |
|-----------|--------|-------------|--------|
| Forces (edge field, repulsive redirect, contradiction routing) | ✅ Done | ~138 | `topology_forces.py` |
| Thermodynamics (evolve, propagate, redistribute) | ✅ Done | ~202 | `topology_thermodynamics.py` |
| Field waves (emit, process, causal chaining) | ✅ Done | ~107 | `topology_waves.py` |
| Region ops (set/adjust/update attribute mutators) | ✅ Done | ~116 | `topology_region_ops.py` |
| Metrics | ✅ Previously extracted | — | `topology_metrics.py` |
| Clustering | ✅ Previously extracted | — | `topology_clustering.py` |
| Persistence | ✅ Previously extracted | — | `topology_persistence.py` |
| Core data models | ⬜ Remaining | ~200 est. | `topology_state_types.py` (partial) |

**Net result:** `topology_state.py` reduced from 1624 → **885 lines** (~45% reduction).

---

## 2. `semantic_segmentation.py` (1210 lines)

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

## 3. `chaos_simulator.py` — ✅ ALREADY EXTRACTED

The 1004-line monolith has already been split into 3 focused modules:
- **`chaos_simulator.py`** (178 lines) — Core orchestrator (`ChaosSimulator` class, `get_chaos_simulator` factory)
- **`chaos_scenarios.py`** (538 lines) — Core types (`FailureMode`, `SeverityLevel`, `FailureScenario`, `FailureScenarios`)
- **`chaos_metrics.py`** (273 lines) — Test suite runner (`ChaosTestSuite`, `OperationalPlaybooks`, `run_chaos_test`)

Backward-compatible `__getattr__` re-exports in `chaos_simulator.py` ensure all existing imports continue working. 5/5 chaos engineering tests pass. No behavioral changes.

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
   `semantic_segmentation.py` (complex DOM logic, no existing tests — needs
   test scaffolding first).
   (`chaos_simulator.py` extraction was already completed.)

## Deferred — Core Product Refactors

The following files are intentionally excluded from the immediate experimental
refactoring plan but are candidates for larger structural refactoring. These are **core product paths**
that require design input before implementation.

| File | Lines | Issue | Effort |
|------|-------|-------|--------|
| `backend/app/main.py` | ~205 | ✅ Completed — app factory refactored. `create_app()` composes middleware/static/routes/lifespan | Medium |
| `backend/app/scraper.py` | ~800 | Single file handles fetch, orchestration, post-processing, and diagnostics | High |
| `backend/app/services/job_runner.py` | ~730 | `run_job()` monolithic — combines discovery, per-url execution, aggregation, finalization | High |
| `backend/app/extraction_orchestrator.py` | ~870 | Multi-layer extraction cascade is correct but implementation is a monolith | Medium |
| `backend/app/job_store.py` + `postgres_repository.py` | ~1500 combined | SQLite and Postgres persistence duplicate model transforms | High |
| `backend/app/worker_queue.py` + `worker_queue_postgres.py` | ~1370 combined | Queue implementations duplicate logic | Medium |

### 4. Rebuild main.py into thin app factory — ✅ COMPLETE

**Goal:** Separate app creation from middleware/route wiring so individual
components (middleware, routers, lifecycle) can be tested in isolation.

**Completed structure:**
```
main.py               →  create_app() factory (~205 lines)
                           Composes: configure_middleware, configure_static,
                           configure_routes, configure_lifespan
app/lifespan.py        →  Startup/shutdown lifecycle hooks
app/routers/            →  Already separated — clean factory wiring
```

**Result:** `main.py` reduced from ~450 to 205 lines. Backward-compatible
re-exports kept for tests and scripts. All 3025+ tests pass.

**Lessons learned:** Import path changes from the refactoring required fixing
9 pre-existing test breakages (monkeypatch sites referencing old import paths,
stale re-exports in `scraper.py`, unused imports, stale `.pyc` files).

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
| 2 | `chaos_simulator.py` → 2 extracted modules | ✅ Complete — 989 lines across 3 modules, 5/5 tests pass |
| 3 | `main.py` → app factory | ✅ Completed — 205 lines, 3025+ tests pass |
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


## Research Shell Boundary (Status: Boundary Established — Quarantine Enforced)

This is the first completed item from the research-shell boundary
establishment: "Freeze product scope and ban research sprawl
from v1". The boundary is now a hard, machine-checkable gate enforced
by a CI invariant, and the legacy product-kernel files have been
brought into compliance.

### What was done

1. **`backend/app/research/__init__.py`** — new module exporting
   `RESEARCH_MODULES` (a `frozenset` of 81 module basenames) and
   `is_research_module()` / `is_research_path()` / `research_summary()`
   helpers. This is the canonical registry. Adding or removing a module
   requires editing this file and is the only sanctioned way to
   re-classify a module.

2. **`backend/app/experimental_startup.py`** — every public function
   (`init_graph_scheduler`, `init_recovery_framework`,
   `init_domain_health_monitor`, `init_gossip_and_heartbeat`,
   `restore_semantic_world_state`, `persist_semantic_world_state`,
   `schedule_gossip_propagation`) now short-circuits to a no-op when
   `settings.ENABLE_EXPERIMENTAL_ROUTES` is False. The new
   `experimental_subsystems_enabled()` helper is the single source of
   truth that the gate consults. `close_postgres_pool()` is intentionally
   NOT gated (Postgres is product-kernel storage, not research).

3. **`backend/app/lifespan.py`** — calls the experimental `init_*`
   functions only when the gate is open. With the default
   `ENABLE_EXPERIMENTAL_ROUTES=False`, the research modules are never
   imported at startup.

4. **`backend/app/main.py`** — the eager import of
   `app.routers.experimental.router` was removed from the top of the
   file and moved inside `configure_routes()` under the
   `if settings.ENABLE_EXPERIMENTAL_ROUTES:` branch. A WARNING is
   logged at app construction when the gate is open in production.
   With the default, the experimental router module is never loaded
   and the `/api/system/*` research endpoints return 404 because they
   are not part of the app.

5. **`.env.example` and `.env.production.example`** — both now contain
   a documented `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=false` entry
   with a comment block explaining the gate.

6. **`scripts/check_research_boundary.py`** — Phase R5 invariant. A
   pure-`ast` scanner that walks every `.py` file under `backend/app/`,
   inspects the *direct children* of each module's `Module` node, and
   fails (exit 1) if any non-research file has a top-level
   `from <research_module> import ...` or `import <research_module>`
   statement. `if TYPE_CHECKING:` blocks are correctly excluded because
   they are wrapped in an `ast.If` node. Wired into `.github/workflows/ci.yml`
   as a mandatory gate.

7. **`backend/app/recovery_handlers.py`** — refactored to use lazy
   imports for the two research modules it depends on
   (`app.recovery_strategies` and `app.domain_runtime_policy`). The
   kernel-level imports (`get_proxy_manager`, `get_selector_memory`)
   remain at the top of the file.

### Tests

- `backend/tests/test_research_boundary.py` (12 cases) — pin down
  the registry: 25 well-known research modules are classified as
  research, 17 well-known product-kernel modules are NOT, prefix
  stripping works, the family summary is complete and sorted, and
  the registry is immutable.
- `backend/tests/test_experimental_gate.py` (13 cases) — every
  public function in `experimental_startup` is verified to be a
  no-op when the gate is off.
- `backend/tests/test_main_routes_gate.py` (4 cases) — verify
  that `app.main` does NOT eagerly import the experimental router,
  that the research paths are absent from the route table when
  the gate is off, that they are present when the gate is on, and
  that a WARNING is logged in production.
- `backend/tests/test_research_kernel_boundary_invariant.py`
  (13 cases) — **Phase R5**: verify the registry contract, the
  `is_research_path` helpers, that the full scan reports zero
  violations, that research files are correctly skipped, that the
  allow-list works, that synthetic violations are detected, that
  unparseable files are handled gracefully, and that
  `if TYPE_CHECKING:` imports are correctly excluded.

### Net effect

With the default `ENABLE_EXPERIMENTAL_ROUTES=False`:

- **Zero research modules in the import graph at startup.** Verified
  by inspection of `lifespan.py` and `main.py`.
- **Zero research endpoints exposed over HTTP.** Verified by the
  route-table test.
- **No product-kernel file may import a research module at top level.**
  Enforced structurally by `scripts/check_research_boundary.py` and
  asserted by 13 tests in `test_research_kernel_boundary_invariant.py`.
- **A clear operator signal at boot** if either is changed
  (WARNING when enabled in production, INFO when disabled).

This is the prerequisite for everything else in this plan: the
remaining refactors (splitting `scraper.py`, `extraction_orchestrator.py`,
`config/`, the worker queues, the postgres repository, etc.) are
mechanical once you can confidently say "this module is product
kernel, that module is research" without tracing every import by hand.

### What is NOT yet done

The registry identifies 81 research modules. The gate prevents
their *initialization* and *HTTP exposure*, AND the CI invariant
prevents any new top-level kernel→research imports. The legacy
product-kernel files (`extraction_orchestrator.py`,
`scraper_recovery_integration.py`, `cleaning_engine.py`,
`state_store.py`, `llm_bridge.py`) have all been brought into
compliance as a side-effect of the R5 cleanup; none of them are
flagged by the invariant. Future refactors that introduce new
kernel→research edges will be caught by the CI gate immediately.
