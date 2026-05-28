# DataForge Studio — Web Extraction & Resilient Crawling Platform

DataForge Studio is a FastAPI + Playwright web extraction platform that extracts structured data from many public web pages using automatic selector discovery, fallback extraction, recovery logic, telemetry, and optional LLM-based schema cleaning.

Unlike basic scrapers, DataForge is built to be resilient and adaptive: it dynamically adjusts to page changes, handles failures with automated recovery pipelines, and maintains a highly efficient, single-row SQLite state store. Results depend on website accessibility, anti-bot controls, page structure, and extraction configuration.

---

## ⚡ Quick Start (5-Minute Demo)

Get up and running locally in just a few steps:

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/Harshit-sehgal/Scraper.git
cd Scraper

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and Playwright browser binaries
pip install -r backend/requirements.txt
python -m playwright install chromium
```

### 2. Configure Environment
Copy the environment template and configure your keys:
```bash
cp .env.example .env
# Edit .env and set your GROQ_API_KEY (optional, fallback engines can run without it)
```

### 3. Start the Server
Start the development server using our helper script:
```bash
./scripts/start.sh
```

### Production Deployment
For production, use the Docker stack (see [backend/README_DEPLOYMENT.md](backend/README_DEPLOYMENT.md)):
```bash
docker compose -f docker-compose.prod.yml up -d
```

This includes:
- **PostgreSQL** for durable storage (or SQLite if not configured)
- **Worker Queue** for async job processing
- **Nginx** reverse proxy
- **Prometheus + Grafana** monitoring stack

Set `DATAFORGE_DATABASE_URL` to switch to Postgres, and `DATAFORGE_WORKER_QUEUE=true` to enable the async worker queue.

**Queue Backend**: Set `DATAFORGE_QUEUE_BACKEND=postgres` to use Postgres-backed queue (recommended for multi-node production). Defaults to SQLite for single-node deployments.

### 4. Create and Scrape a Job
Open another terminal (with `.venv` activated) and run the manual test interface to quickly launch a demonstration extraction job:
```bash
python scripts/manual_test.py test-job
```
This will register and execute a live extraction job, showing real-time logs and progress on your terminal!

---

## 🖥️ Interactive Dashboards

Once the platform is running, access the user interfaces:

| Interface | URL | Purpose |
|-----|-------------|---------|
| **DataForge Studio Dashboard** | `http://localhost:8000/app` | Visually manage, monitor, and run extraction jobs. |
| **Semantic Reliability Dashboard** | `http://localhost:8000/dashboard` | View real-time crawler telemetry, selector drift metrics, and graph topology. |
| **Interactive API Swagger Docs** | `http://localhost:8000/docs` | Standard FastAPI OpenAPI sandbox for developers. |

---

## 🛠️ Manual Testing CLI

The project includes an interactive, rich CLI test tool for verification:

### Interactive Menu
```bash
python scripts/manual_test.py
```
This opens a terminal menu with quick options to:
- Check server health, live jobs, and configuration limits
- Explore the semantic field topology (regions, edges, clusters)
- View real-time observability telemetry and health index
- Create and monitor a real scraping job (manual or auto/discovery mode)
- Browse synthesized crystalline knowledge records
- Run the full pytest suite

### Quick Command Line Actions
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

---

## ⚙️ REST API Endpoints

DataForge Studio exposes a rich, RESTful API interface for programmatic jobs and system diagnostics:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Production-grade lightweight health check endpoint. |
| GET | `/api/system/status` | Server status, job counts, and runtime config. |
| GET | `/api/system/topology` | Full semantic field state (regions, edges, clusters). |
| GET | `/api/system/observability` | Telemetry, health index, and drift heatmaps. |
| GET | `/api/system/crystalline` | Synthesized knowledge records. |
| GET | `/api/system/export/knowledge`| Export knowledge manifold. |
| POST | `/api/jobs` | Create a new scraping / extraction job. |
| GET | `/api/jobs/{id}` | Get status and results for a job. |
| DELETE | `/api/jobs/{id}` | Delete a job (moves it to the recycle bin). |
| GET | `/api/recycle_bin` | List deleted jobs. |
| POST | `/api/recycle_bin/{id}/restore`| Restore a deleted job. |
| DELETE | `/api/recycle_bin/{id}` | Permanently delete a job. |
| POST | `/api/system/scheduler/step` | Trigger cognitive scheduler manually. |
| GET | `/api/system/search?query=...`| Topological search. |
| GET | `/metrics` | Prometheus metrics endpoint. In production it is blocked by public Nginx and scraped internally by Prometheus over the Docker network. |

---

## 🧠 Cognitive Substrate & Research Layer (Advanced)

For developers and researchers interested in the under-the-hood intelligence layer, DataForge Studio uses a **topology-native dynamical system** to align extracted meaning. This is detailed in our custom `GEMINI.md` ontology:

1. **Unified Semantic World State**: A canonical substrate in `app/semantic_world_state/` that serves as the single source of truth for all cognition engines.
2. **Meaning from Topology**: Meaning emerges from relational graph energy and stability, not simple regex matching.
3. **Contradiction-Aware Reasoning**: Semantic conflicts propagate as energy pressure through the graph via `ExclusionEdge` topology.
4. **Adaptive Memory**: Structural motifs are reinforced by extraction successes and decayed by time/neglect to counter element change (selector decay).

For deep structural details and research notes, see [ARCHITECTURE.md](backend/ARCHITECTURE.md) and [RESEARCH_NOTES.md](backend/RESEARCH_NOTES.md).
