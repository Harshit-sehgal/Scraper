#!/bin/bash
# Scraper Benchmark Runner
#
# Two modes:
#
#   1. Default (no flag) — runs the deterministic in-corpus unit benchmarks
#      that ship with the repo. These are CI-safe (no live-internet calls)
#      and exercise the extraction engine against canned HTML + golden
#      dataset fixtures.
#
#   2. Live internet benchmarks (DATAFORGE_RUN_LIVE_BENCHMARKS=1) — runs
#      scripts/live_benchmark.py against quotes.toscrape.com (and any
#      custom URL via -- --url=…). These hit real websites and are NOT
#      suitable for normal CI; the workflow file only enables them on
#      manual dispatch with the "live-benchmarks" input.
set -e

echo "=== DataForge Scraper: Benchmark Runner ==="

# 1. Setup environment
export PYTHONPATH=backend
PYTHON_EXEC="./backend/venv/bin/python"

if [ ! -f "$PYTHON_EXEC" ]; then
    echo "Virtualenv not found at $PYTHON_EXEC. Falling back to system python."
    PYTHON_EXEC="python3"
fi

# 2. Install Playwright browsers (if needed)
$PYTHON_EXEC -m playwright install chromium

# 3. Live-internet benchmarks (opt-in)
if [ "${DATAFORGE_RUN_LIVE_BENCHMARKS:-0}" = "1" ]; then
    echo "Running live-internet benchmarks (DATAFORGE_RUN_LIVE_BENCHMARKS=1)…"
    $PYTHON_EXEC scripts/live_benchmark.py "$@"
else
    echo "Skipping live-internet benchmarks (set DATAFORGE_RUN_LIVE_BENCHMARKS=1 to enable)."
fi

# 4. Run standard in-corpus unit benchmarks (always safe for CI)
echo "Running in-corpus unit benchmarks..."
$PYTHON_EXEC -m pytest backend/tests/test_field_waves.py "$@"
$PYTHON_EXEC -m pytest backend/tests/test_field_validator.py "$@"
$PYTHON_EXEC -m pytest backend/tests/test_extraction_precision.py "$@"
$PYTHON_EXEC -m pytest backend/tests/test_accuracy.py "$@"

echo "=== Selected benchmark and unit checks completed ==="
