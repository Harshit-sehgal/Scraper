#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"
export PYTHONPATH=.
exec ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning