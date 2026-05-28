# DataForge Scraper

DataForge Scraper is a pre-production web extraction platform built with FastAPI and Playwright. It focuses on job orchestration, basic telemetry, and adaptive extraction, with production-hardening work actively ongoing.

**Disclaimer**: Extraction results depend heavily on website accessibility, anti-bot controls, page structure, authentication requirements, and extraction configuration. This system cannot independently recover from all failures without human review.

---

## ⚡ Quick Start

Get up and running locally:

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
# Edit .env and set your required API keys.
```

### 3. Start the Server
Start the development server using the helper script:
```bash
./scripts/start.sh
```

### Production Deployment
For production, use the Docker stack (see [backend/README_DEPLOYMENT.md](backend/README_DEPLOYMENT.md)):
```bash
docker compose -f docker-compose.prod.yml up -d
```

This includes:
- **PostgreSQL** for durable storage
- **Worker Queue** for async job processing
- **Nginx** reverse proxy
- **Prometheus + Grafana** monitoring stack

Set `DATAFORGE_DATABASE_URL` to switch to Postgres, and `DATAFORGE_WORKER_QUEUE=true` to enable the async worker queue.

---

## 🖥️ Interactive Dashboards

Once the platform is running, access the user interfaces:

| Interface | URL | Purpose |
|-----|-------------|---------|
| **DataForge Studio Dashboard** | `http://localhost:8000/app` | Visually manage, monitor, and run extraction jobs. |
| **Interactive API Swagger Docs** | `http://localhost:8000/docs` | Standard FastAPI OpenAPI sandbox for developers. |

---

## ⚙️ REST API Endpoints

DataForge Studio exposes a RESTful API interface for programmatic jobs and system diagnostics.
Access to operational endpoints requires valid `X-API-Key` or `Authorization: Bearer` headers.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Lightweight health check endpoint. |
| GET | `/api/system/status` | Server status, job counts, and runtime config. |
| POST | `/api/jobs` | Create a new extraction job. |
| GET | `/api/jobs/{id}` | Get status and results for a job. |
| DELETE | `/api/jobs/{id}` | Delete a job (moves it to the recycle bin). |
| GET | `/metrics` | Prometheus metrics endpoint. |

---

## 🛠️ Verification & Testing

The project includes an interactive CLI test tool and several verification scripts:

```bash
# Full release readiness checks (Tests, compilation, pyflakes)
./scripts/verify_release.sh

# Production env validation
python scripts/check_prod_env.py --env-file .env

# Run the full test suite
PYTHONPATH=backend pytest backend/tests/ -q
```
