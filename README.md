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

## Prerequisites

- Python 3.10+
- A [Groq](https://console.groq.com) API key for AI-powered structuring and insight generation

## Quick Start

### 1. Environment Setup

```bash
# Clone and enter the project
cd scraper

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy the environment template and add your Groq API key
cp .env.example .env
# Edit .env: set GROQ_API_KEY=your_key_here
```

### 2. Start the Server

```bash
# Option A: Using the startup script (recommended)
./scripts/start.sh

# Option B: Directly with uvicorn
uvicorn backend.app.main:app --reload
```

### 3. Open the Dashboard

| URL | Description |
|-----|-------------|
| `http://localhost:8000/app` | DataForge Studio — Job management UI |
| `http://localhost:8000/dashboard` | Semantic Reliability Dashboard (topology, telemetry, drift) |
| `http://localhost:8000/docs` | Interactive API documentation (Swagger) |

## Manual Testing

The project includes a comprehensive CLI test tool for manual testing:

### Interactive Menu

```bash
python scripts/manual_test.py
```

This opens an interactive menu with options to:
- Check server health and job counts
- Explore the semantic field topology (regions, edges, clusters)
- View observability telemetry and health index
- Trigger the cognitive scheduler manually
- Create and monitor a real scraping job (manual or auto mode)
- Browse synthesized crystalline knowledge records
- Run the full pytest suite

### Quick Commands

```bash
# Quick health check
python scripts/manual_test.py health

# Show field topology and metrics
python scripts/manual_test.py topology

# Create a test job (manual mode) and monitor progress
python scripts/manual_test.py test-job

# Create a test job (auto/discovery mode)
python scripts/manual_test.py test-job-auto

# View observability & health index
python scripts/manual_test.py observability

# Run all checks sequentially
python scripts/manual_test.py all

# Run the full test suite
python scripts/manual_test.py tests
```

## Manual Test Scripts

Dedicated test scripts are in `backend/tests/`:

```bash
# API-based manual tests (requires running server)
python backend/tests/manual_test_api.py
python backend/tests/manual_run_manual_test.py

# Workflow tests (create, delete, recycle)
python backend/tests/manual_test_workflow.py
```

## Verification

Run the full cognitive stability suite:
```bash
.venv/bin/pytest backend/tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/system/status` | Server status, job counts, runtime config |
| GET | `/api/system/topology` | Full semantic field state (regions, edges, clusters) |
| GET | `/api/system/observability` | Telemetry, health index, heatmaps |
| GET | `/api/system/crystalline` | Synthesized knowledge records |
| GET | `/api/system/export/knowledge` | Export knowledge manifold |
| POST | `/api/jobs` | Create a new scraping job |
| GET | `/api/jobs/{id}` | Get job status and results |
| DELETE | `/api/jobs/{id}` | Delete a job (moves to recycle bin) |
| GET | `/api/recycle_bin` | List deleted jobs |
| POST | `/api/recycle_bin/{id}/restore` | Restore a deleted job |
| DELETE | `/api/recycle_bin/{id}` | Permanently delete a job |
| POST | `/api/system/scheduler/step` | Trigger cognitive scheduler |
| POST | `/api/system/refactor/compress` | Trigger manifold compression |
| GET | `/api/system/search?query=...` | Topological search |
| POST | `/api/system/merge/knowledge` | Merge external knowledge |

