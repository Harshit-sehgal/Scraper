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

## Deferred

The following medium-large files are intentionally excluded from this plan
because they have active development, are core product (not experimental),
or have acceptable complexity levels:
- `backend/app/selector_discovery_url.py` — core product
- `backend/app/scraper.py` — core product, orchestration is the point
- `backend/app/main.py` — FastAPI entry point, naturally grows
- `backend/app/network_extractor.py` — core product
- `backend/app/extraction_orchestrator.py` — core product, well-structured

These should be reviewed for internal refactoring as needed but are not
blockers.
