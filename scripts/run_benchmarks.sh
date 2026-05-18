#!/bin/bash
# Scraper Benchmark CI Runner
set -e

echo "=== DataForge Scraper: Hostile Benchmarks ==="

# 1. Setup environment
export PYTHONPATH=backend
PYTHON_EXEC="./backend/venv/bin/python"

if [ ! -f "$PYTHON_EXEC" ]; then
    echo "Virtualenv not found at $PYTHON_EXEC. Falling back to system python."
    PYTHON_EXEC="python3"
fi

# 2. Install Playwright browsers (if needed)
$PYTHON_EXEC -m playwright install chromium

# 3. Run hostile benchmarks
echo "Running benchmarks..."
$PYTHON_EXEC backend/tests/hostile_benchmarks.py

# 4. Run standard unit tests
echo "Running unit tests..."
$PYTHON_EXEC -m pytest backend/tests/test_field_waves.py
$PYTHON_EXEC -m pytest backend/tests/test_field_validator.py
$PYTHON_EXEC -m pytest backend/tests/test_extraction_precision.py
$PYTHON_EXEC -m pytest backend/tests/test_accuracy.py

echo "=== All checks PASSED ==="
