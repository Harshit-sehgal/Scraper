#!/usr/bin/env bash
# =============================================================================
# DataForge Studio — Dev Server Starter
# =============================================================================
# Starts the FastAPI server with hot-reload for development.
# Usage:
#   ./scripts/start.sh            # Start server on default port 8000
#   PORT=9000 ./scripts/start.sh  # Start server on custom port
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# ─── Detect virtual environment ────────────────────────────────────────────
VENV_DIR=""
for candidate in ".venv" "venv" "env"; do
    if [ -f "$PROJECT_DIR/$candidate/bin/activate" ]; then
        VENV_DIR="$PROJECT_DIR/$candidate"
        break
    fi
done

if [ -z "$VENV_DIR" ]; then
    echo "❌ No virtual environment found. Create one first:"
    echo "   python3 -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r backend/requirements-dev.lock.txt"
    exit 1
fi

# ─── Check .env ────────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  No .env file found. Copying from .env.example..."
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        echo "   Created .env — edit it to add your GROQ_API_KEY"
    else
        echo "   No .env.example found either. Create a .env file manually."
    fi
fi

# ─── Activate venv ─────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ─── Check runtime dependencies ─────────────────────────────────────────────
if ! python - <<'PY'
import importlib
from pathlib import Path

missing = []

for label, module_name in (
    ("fastapi", "fastapi"),
    ("playwright", "playwright.sync_api"),
):
    try:
        importlib.import_module(module_name)
    except Exception:
        missing.append(label)

if not any(importlib.util.find_spec(name) for name in ("ddgs", "duckduckgo_search")):
    missing.append("ddgs or duckduckgo_search")

if missing:
    raise SystemExit("Missing dependencies: " + ", ".join(missing))

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        chromium_path = Path(playwright.chromium.executable_path)
    if not chromium_path.exists():
        raise SystemExit(
            "Missing Playwright Chromium browser. Run: python -m playwright install chromium"
        )
except SystemExit:
    raise
except Exception as exc:
    raise SystemExit(f"Playwright browser check failed: {exc}") from exc

print("Dependency check passed")
PY
then
    echo "❌ Runtime dependencies not installed or incomplete. Run:"
    echo "   pip install -r backend/requirements-dev.lock.txt"
    echo "   python -m playwright install chromium"
    exit 1
fi

# ─── Port ──────────────────────────────────────────────────────────────────
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         DataForge Studio — Dev Server                       ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  API:       http://localhost:$PORT                            "
echo "║  Dashboard: http://localhost:$PORT/app                       "
echo "║  Replay UI: http://localhost:$PORT/dashboard                 "
echo "║  Docs:      http://localhost:$PORT/docs                      "
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

export PYTHONPATH="$PROJECT_DIR/backend:${PYTHONPATH:-}"
exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT" --log-level info
