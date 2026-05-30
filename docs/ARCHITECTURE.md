# Architecture

## Reality Summary

DataForge Scraper is a FastAPI application with browser-assisted extraction, job state management, result export, telemetry, and experimental adaptive/semantic components. It is pre-production. The codebase is larger than a simple scraper, but several advanced parts are implemented without production-like validation.

## Backend

- Entry point: `backend/app/main.py`
- Routers: `backend/app/routers/jobs.py`, `exports.py`, `scraper.py`, `operator.py`
- Models: `backend/app/models.py`
- Config: `backend/app/config.py`

Status: verified import and local tests.

## Scraper and Extraction

The scraper uses Playwright/browser flows, HTML utility helpers, selector discovery, visible-text extraction, network payload extraction, schema-field handling, and zero-result classification.

Status: implemented and partially verified. Local Playwright E2E tests passed in an environment with browser/socket permissions.

## Job Orchestration

Jobs can be created, listed, fetched, canceled, deleted, recycled, and exported. Worker queue support exists and production worker startup now validates required production env.

Status: implemented and locally verified for basic API flows. Distributed production behavior is not fully validated.

## Storage

SQLite-style local state remains the default path. Postgres repository and queue support exist.

Status: SQLite paths are locally tested. Postgres support is implemented but not production-validated until real Postgres CI/service tests pass.

## Metrics and Telemetry

Metrics and telemetry collectors exist. `/metrics` emits Prometheus-style data. Production Nginx blocks public `/metrics`; direct backend exposure should set `DATAFORGE_METRICS_TOKEN`.

Status: implemented and partially verified.

## Dashboard

The main dashboard and semantic dashboard are static frontend files served from `/app` and `/dashboard`. The dashboard uses polling, not WebSocket/SSE streaming.

Status: implemented for internal/private use. API key storage in `localStorage` remains a security limitation.

## Security

The backend has API key middleware, user/operator/admin RBAC dependencies on sensitive routes, request-size limiting, SSRF-oriented URL checks, CORS config, and production env validation.

Status: partially verified. A complete route-level authorization matrix and production threat model remain open work.

## Production Deployment

The repo includes Dockerfile, production compose, Nginx, Prometheus, Grafana, env examples, smoke scripts, and release verification scripts.

Status: implemented but not end-to-end validated in this audit.

## Advanced Components

The following components are **EXPERIMENTAL / NOT FULLY VALIDATED**:

- **Semantic world state** — ⚠️ Implemented but not validated in production-like scenarios.
- **Topology engine** — ⚠️ Site modeling is implemented; effectiveness on varied sites is unproven.
- **Replay buffer** — ⚠️ Replay functionality exists but not hardened for production.
- **Strategy evolution** — ⚠️ Per-domain strategy learning is implemented but untested in real-world conditions.
- **Selector memory** — ⚠️ Learned pattern storage exists; convergence behavior unknown.
- **Recovery logic** — ⚠️ Recovery strategies are defined; simulated benchmarks don't prove real-world effectiveness.
- **Adaptive extraction** — ⚠️ Self-tuning parameters exist; real-world reliability not validated.

**Status**: implemented but unevenly validated. These components should NOT be described as fully autonomous or fully self-healing.
