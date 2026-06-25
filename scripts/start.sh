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
    echo "   pip install -e \".[dev]\""
    exit 1
fi

# ─── Check .env ────────────────────────────────────────────────────────────
# F-SCRIPT-003: refuse to silently create a placeholder ``.env``. The
# prior behaviour ran ``cp .env.example .env`` and exited 0, so an
# operator who forgot to set ``GROQ_API_KEY`` (or any other secret)
# would boot the server with a placeholder-keyed .env and only learn
# the failure later. The fix refuses by default and lets a developer
# opt in via ``DATAFORGE_ACCEPT_PLACEHOLDER_ENV=1`` when they
# explicitly want the example file.
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "❌ No .env file found in $PROJECT_DIR." >&2
    echo "   Create one with real production secrets before starting the server." >&2
    echo "   If you want a placeholder .env for local experimentation only," >&2
    echo "   rerun with: DATAFORGE_ACCEPT_PLACEHOLDER_ENV=1 $0" >&2
    if [ "${DATAFORGE_ACCEPT_PLACEHOLDER_ENV:-0}" != "1" ]; then
        exit 1
    fi
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        echo "   Placeholder .env copied (DATAFORGE_ACCEPT_PLACEHOLDER_ENV=1)." >&2
        echo "   Replace placeholder secrets with real values before any real use." >&2
    else
        echo "   No .env.example found either. Create a .env file manually before running." >&2
        exit 1
    fi
fi

# ─── Activate venv ─────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ─── Check runtime dependencies ─────────────────────────────────────────────
if ! python - <<'PY'
import importlib

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

# Verify the Playwright Chromium browser binary exists on disk without
# spawning a driver process (faster and avoids a stray Chrome/Chromium
# instance lingering after this check).
try:
    from playwright.sync_api import sync_playwright
    from pathlib import Path

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
    echo "   pip install -e \".[dev]\""
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
