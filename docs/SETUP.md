# Setup

**Last refreshed:** 2026-06-08

## Local Python Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.lock.txt
playwright install chromium
```

## Run The Backend

```bash
PYTHONPATH=backend python3 -m uvicorn app.main:app --reload
```

Open `http://localhost:8000/app/` for the dashboard.

> **Note:** The dev server mounts the `frontend/` directory at the `/app`
> prefix via FastAPI's `StaticFiles`. Assets (`app.js`, `styles.css`,
> `favicon.svg`) use **relative paths** in `index.html` so they resolve
> correctly to `/app/app.js` etc. If you ever see 404s for these assets
> in the browser console, check that the page URL ends with a trailing
> slash — `/app/` not `/app` — so relative paths resolve from
> the `/app/` directory rather than the server root. Production deployments
> behind nginx use different path resolution (see `nginx.conf`) and are
> not affected by this quirk.

## Local Configuration

```bash
cp .env.example .env
```

For local development, SQLite-style state is enough. Use `DATAFORGE_STATE_FILE_PATH` for the jobs state file. `DATAFORGE_STATE_FILE` remains as deprecated compatibility only.

## Optional API Keys

When API keys are configured, `/api/*` routes require credentials:

```bash
DATAFORGE_API_KEY=local-user-key
DATAFORGE_OPERATOR_API_KEY=local-operator-key
DATAFORGE_ADMIN_API_KEY=local-admin-key
```

Use strong random values outside local development.

## Rate Limiting

The API applies dual-layer rate limiting out of the box:

- **Global cap**: `600 requests/minute` across all clients (`DATAFORGE_RATE_LIMIT_GLOBAL`)
- **Per-IP cap**: `100 requests/minute` per client (`DATAFORGE_RATE_LIMIT_PER_IP`)

Both tiers must be satisfied for a request to proceed. Per-IP tracking can be disabled
with `DATAFORGE_RATE_LIMIT_PER_IP_ENABLED=false`.

In production/staging, rate limiting auto-promotes to the shared database-backed store
for multi-worker consistency. See `docs/API.md` for the full rate limiting reference.

## Common Commands

Use explicit local settings to avoid accidental Postgres dependency:

```bash
# Check syntax
python3 -m compileall -q backend scripts architecture_validator.py

# Validate architecture
python3 architecture_validator.py

# Collect tests without running
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=

# Run local test suite (SQLite mode)
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests -o addopts=

# Lint (ruff replaces pyflakes)
python3 -m ruff check backend/app backend/tests scripts
python3 -m ruff format --check backend/app backend/tests scripts

# Type check (ignores missing imports for packages)
python3 -m mypy backend/app --ignore-missing-imports

# Research-shell boundary invariant (R5)
PYTHONPATH=backend python3 scripts/check_research_boundary.py

# Dependency bounds validation
python3 scripts/validate_dependency_bounds.py

# Or run the full local suite (does not require Docker)
make validate
# or, equivalently:
bash scripts/verify_all.sh
```
