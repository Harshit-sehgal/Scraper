# DataForge Studio — Semantic Cognition Substrate

DataForge Studio is a research-grade semantic cognition architecture designed for topology-driven web extraction.

## Core Architectural Mandates

1.  **Unified Semantic World State**: A canonical substrate in `app/semantic_world_state.py` that serves as the single source of truth for all cognition engines.
2.  **Meaning from Topology**: Meaning emerges from relational graph energy and stability, not adjacency or regex labels.
3.  **Contradiction-Aware Reasoning**: Semantic conflicts propagate as energy pressure through the graph via `ExclusionEdge` topology.
4.  **Continuous Evolution**: Inference is an iterative graph relaxation process that converges toward minimum energy equilibrium.
5.  **Event-Driven Signal Propagation**: Instability triggers asynchronous updates through a decentralized event dispatcher.
6.  **Adaptive Memory**: Structural motifs are reinforced by success and decayed by time/neglect.

## Brain Architecture

*   **Substrate Layer**: `SemanticWorldState` (Global persistent topology).
*   **Cognition Layer**: `InferenceEngine` (Graph thermodynamics and energy minimization).
*   **Signal Layer**: `EventDispatcher` & `GraphUpdateScheduler` (Topological signal propagation).
*   **Memory Layer**: `MotifLearner` (Adaptive reinforcement/decay).
*   **Observer Layer**: `TopologicalDiagnostics` (Uncertainty heatmaps and pressure fields).

## Getting Started

1.  Set up your `.env` with a `GROQ_API_KEY`.
2.  Run the API: `uvicorn backend.app.main:app --reload`
3.  Launch the Dashboard: `http://localhost:8000/app`

## Verification

Run the full cognitive stability suite:
```bash
.venv/bin/pytest backend/tests/
```
Current Status: **83/83 passed**.
