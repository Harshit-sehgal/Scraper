# Setup

## Local Python Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium
```

## Run The Backend

```bash
PYTHONPATH=backend python3 -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/app` for the dashboard.

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

## Common Commands

```bash
PYTHONPATH=backend python3 -m pytest --collect-only -q -o addopts=
PYTHONPATH=backend python3 -m pytest -q
python3 -m pyflakes backend/app scripts architecture_validator.py
python3 -m mypy backend/app --ignore-missing-imports
```
