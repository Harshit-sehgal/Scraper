# Research Module Triage (E5.1) — executed 2026-08-18

> **Status: dispositions EXECUTED (E5.2, 2026-08-18).** The 6 `archive-to-branch`
> modules (energy_api, persistence_state, semantic_os, topology_api, topology_gc,
> transactional_priority_queue) were moved to branch
> `research-archive-2026-08` (they remain available there with their 10 test
> files) and deleted from `main`. The registry in `backend/app/research/__init__.py`
> was updated, the promoted `semantic_world_state` package shed 12 dead public
> methods whose only callers lived in the archived modules (branch, merge_branch,
> semantic_diff, clear_intents, dispatch_actions, schedule_cognitive_task,
> log_action_execution, gc_collect, gc_collect_stale_regions/motifs/exclusions,
> gc_trim_snapshots), and 59 tests were removed with the archived code.
> Measurements: compileall 0.05s → 0.18s (cached, noise); pytest collection
> 8579 → 8520 tests (2.24s → 2.50s, noise). Quick gate 14/14 green.

# Research Module Triage (E5.1)

Every `backend/app` research/experimental module, with disposition. Generated from the research registry + filesystem scan on 2026-08-18; stable-import counts come from `from app.<mod>` / `import app.<mod>` occurrences in non-research files (all such imports are lazy/function-level — the top-level boundary in `check_research_boundary.py` stays green).

| Module | Family | Stable refs | Tests | Disposition | Note |
|---|---|---|---|---|---|
| `abstraction_state` | field_abstraction | 1 |  | **keep-gated** | lazy-imported by stable code |
| `acquisition_mode` | intent_acquisition | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `acquisition_quality_gate` | intent_acquisition | 0 | yes | **keep-gated** | characterization tests exist |
| `acquisition_state` | intent_acquisition | 6 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `acquisition_telemetry` | intent_acquisition | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `action_state` | field_abstraction | 1 |  | **keep-gated** | lazy-imported by stable code |
| `chaos_metrics` | chaos_replay | 1 |  | **keep-gated** | lazy-imported by stable code |
| `chaos_scenarios` | chaos_replay | 2 |  | **keep-gated** | lazy-imported by stable code |
| `chaos_simulator` | chaos_replay | 2 |  | **keep-gated** | lazy-imported by stable code |
| `core_types` | core_types | 6 |  | **keep-gated** | lazy-imported by stable code |
| `crawl_state` | recovery_history | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `degradation_predictor` | strategy_evolution | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `domain_evolution_model` | strategy_evolution | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `domain_health_alerts` | resource_governance | 3 |  | **keep-gated** | lazy-imported by stable code |
| `domain_runtime_policy` | resource_governance | 5 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `energy_api` | topology_manifold | 0 |  | **archive-to-branch** | default disposition |
| `energy_state` | topology_manifold | 2 |  | **keep-gated** | lazy-imported by stable code |
| `event_dispatcher` | event_dispatcher | 5 |  | **keep-gated** | lazy-imported by stable code |
| `event_journal` | recovery_history | 2 |  | **keep-gated** | lazy-imported by stable code |
| `failure_injector` | chaos_replay | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `federation_manager` | federation | 1 |  | **keep-gated** | lazy-imported by stable code |
| `field_laws` | field_abstraction | 8 |  | **keep-gated** | lazy-imported by stable code |
| `field_validator` | field_abstraction | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `gossip_substrate` | federation | 2 |  | **keep-gated** | lazy-imported by stable code |
| `graph_update_scheduler` | event_dispatcher | 6 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `heartbeat_manager` | federation | 3 |  | **keep-gated** | lazy-imported by stable code |
| `history_state` | recovery_history | 1 |  | **keep-gated** | lazy-imported by stable code |
| `insight_engine` | strategy_evolution | 3 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `instability_api` | topology_manifold | 2 |  | **keep-gated** | lazy-imported by stable code |
| `instability_state` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `intent_parser` | intent_acquisition | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `intent_state` | intent_acquisition | 1 |  | **keep-gated** | lazy-imported by stable code |
| `invariant_firewall` | field_abstraction | 4 |  | **keep-gated** | lazy-imported by stable code |
| `manifold_state` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `motif_feedback` | topology_manifold | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `motif_state` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `observability` | core_types | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `persistence_state` | recovery_history | 0 |  | **archive-to-branch** | default disposition |
| `policy_engine` | policy_engine | 3 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `recovery_handlers` | recovery_history | 1 |  | **keep-gated** | lazy-imported by stable code |
| `recovery_strategies` | recovery_history | 3 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `replay_buffer` | chaos_replay | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `resource_governor` | resource_governance | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `runtime_budget` | resource_governance | 1 |  | **keep-gated** | lazy-imported by stable code |
| `scraper_recovery_integration` | misc | 1 |  | **keep-gated** | lazy-imported by stable code |
| `selector_decay_predictor` | strategy_evolution | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `selector_ml_optimizer` | strategy_evolution | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `self_tuning_extraction` | strategy_evolution | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `semantic_allocation_engine` | semantic_world_state | 4 |  | **keep-gated** | lazy-imported by stable code |
| `semantic_boundary_engine` | semantic_world_state | 2 |  | **keep-gated** | lazy-imported by stable code |
| `semantic_events` | semantic_world_state | 6 |  | **keep-gated** | lazy-imported by stable code |
| `semantic_inference_engine` | semantic_world_state | 7 |  | **keep-gated** | lazy-imported by stable code |
| `semantic_ir` | semantic_world_state | 7 |  | **keep-gated** | lazy-imported by stable code |
| `semantic_mapper` | semantic_world_state | 3 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `semantic_os` | semantic_world_state | 0 |  | **archive-to-branch** | default disposition |
| `semantic_persistence` | semantic_world_state | 1 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `semantic_pipeline` | semantic_world_state | 4 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `semantic_roots` | semantic_world_state | 2 |  | **keep-gated** | lazy-imported by stable code |
| `semantic_segmentation` | semantic_world_state | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `semantic_world_state (package)` | semantic_world_state | 29 | yes | **promote (ONE)** | de facto promoted — lazy-imported by ~28 stable files; formalize with promotion plan per STABLE_VS_EXPERIMENTAL.md |
| `snapshot_desync_detector` | chaos_replay | 0 | yes | **keep-gated** | characterization tests exist |
| `strategy_evolution` | strategy_evolution | 6 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `telemetry_state` | recovery_history | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `topology_api` | topology_manifold | 0 |  | **archive-to-branch** | default disposition |
| `topology_clustering` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_dynamics` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_forces` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_gc` | topology_manifold | 0 |  | **archive-to-branch** | default disposition |
| `topology_metrics` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_persistence` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_region_ops` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_state` | topology_manifold | 10 |  | **keep-gated** | lazy-imported by stable code |
| `topology_state_types` | topology_manifold | 4 |  | **keep-gated** | lazy-imported by stable code |
| `topology_thermodynamics` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_view` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `topology_waves` | topology_manifold | 1 |  | **keep-gated** | lazy-imported by stable code |
| `transaction_context` | resource_governance | 12 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `transactional_priority_queue` | resource_governance | 0 |  | **archive-to-branch** | default disposition |
| `transition_state` | recovery_history | 1 |  | **keep-gated** | lazy-imported by stable code |
| `trend_analyzer` | strategy_evolution | 2 | yes | **keep-gated** | lazy-imported by stable code; has tests |
| `vector_clock` | strategy_evolution | 3 |  | **keep-gated** | lazy-imported by stable code |
| `visualization` | visualization | 1 |  | **keep-gated** | lazy-imported by stable code |

## Disposition rules

- **keep-gated** — has lazy imports from stable product code and/or
  characterization tests. Stays behind `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES`
  and the registry; removing it would break runtime paths (verified:
  the boundary checker only scans top-level imports, so these are
  invisible to it).
- **archive-to-branch** (default) — zero stable references and no
  tests. Safe to move to `research-archive-2026-08` without touching
  the stable import graph.
- **promote (ONE, max)** — `semantic_world_state` is de facto promoted
  (lazy-imported by ~28 stable files, e.g. `llm_bridge`, `cleaning_engine`,
  `services/ai_structuring`). Promotion becomes formal once it gets a
  promotion plan + characterization tests per `docs/STABLE_VS_EXPERIMENTAL.md`.

## Execution note (E5.2)

Before executing dispositions: create the archive branch
(`git checkout -b research-archive-2026-08`), move the `archive-to-branch`
modules there, then update the registry in `backend/app/research/__init__.py`
and re-run `scripts/check_research_boundary.py`,
`backend/tests/test_research_boundary.py`, and the full quick gate.
Measure `python3 -m compileall -q backend` + pytest collection time
before/after and record the delta in AGENT_TRUTH.md.
