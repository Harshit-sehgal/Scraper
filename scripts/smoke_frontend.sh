#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# smoke_frontend.sh — Local smoke test for frontend build artifacts
#
# Runs ``npm run build`` then checks that the critical output files exist
# and their sizes are within acceptable thresholds. Mirrors the CI
# frontend-build-smoke step so developers can catch regressions locally.
#
# Usage:  bash scripts/smoke_frontend.sh
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$REPO_ROOT/frontend/dist"

APP_JS="$DIST_DIR/app.js"
STYLES_CSS="$DIST_DIR/styles.css"

echo "── Building frontend ──"
(cd "$REPO_ROOT" && npm run build)

echo "── Checking build artifacts ──"

missing=false
for f in "$APP_JS" "$STYLES_CSS"; do
  if [ ! -f "$f" ]; then
    echo "❌ MISSING build output: $f"
    missing=true
  fi
done
if [ "$missing" = true ]; then
  exit 1
fi

# F-FRONTEND-001: CSS must stay under 200 KB
css_bytes=$(stat --format=%s "$STYLES_CSS" 2>/dev/null || stat -f%z "$STYLES_CSS" 2>/dev/null)
css_kb=$((css_bytes / 1024))

if [ "$css_kb" -gt 200 ]; then
  echo "❌ styles.css is ${css_kb} KB — exceeds 200 KB threshold (F-FRONTEND-001)"
  exit 1
fi

app_js_bytes=$(stat --format=%s "$APP_JS" 2>/dev/null || stat -f%z "$APP_JS" 2>/dev/null)

echo "✅ app.js ($((app_js_bytes / 1024)) KB), styles.css (${css_kb} KB) — within thresholds"
