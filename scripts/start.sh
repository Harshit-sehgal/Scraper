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
    echo "   pip install -r requirements.txt"
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

# ─── Check key dependency ──────────────────────────────────────────────────
if ! python -c "import fastapi" 2>/dev/null; then
    echo "❌ Dependencies not installed. Run:"
    echo "   pip install -r requirements.txt"
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

exec uvicorn backend.app.main:app --reload --host "$HOST" --port "$PORT" --log-level info
