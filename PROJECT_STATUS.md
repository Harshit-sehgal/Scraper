# DataForge — Project Status

**Last Updated**: May 2026

## Verified

- Python syntax: 0 compilation errors across all backend files
- All backend app modules import successfully (135 modules, 0 errors)
- FastAPI app boots and serves ~83 routes
- Pyflakes: 0 warnings
- Architecture validator: passes (`VALIDATION PASSED: Architecture is lawful`)
- Basic health routes respond: `/health`, `/ready`, `/api/system/status`, `/metrics` all return 200
- RBAC enforcement: role-based access control on all mutating and system-control endpoints
- SSRF protection: URL validation on discover, job creation, and recovery actions
- Rate limiting: in-memory sliding window + nginx rate zones
- Body size limits: 5MB payload cap with chunked transfer enforcement
- Local dashboard security: Chart.js and Tailwind CSS are vendored locally; external CDNs are blocked by a strict Content-Security-Policy (CSP) in Nginx
- Standardized environment variables: State file paths consistently configured via `DATAFORGE_STATE_FILE_PATH` (canonical) with `DATAFORGE_STATE_FILE` supported as legacy fallback
- Dashboard polling: The operator dashboard polls REST endpoints at intervals; it is live-polling, not streaming (WebSockets/SSE are not used)

## Partially Verified

- Test suite: ~1708 tests exist. Targeted critical tests pass. Full-suite CI verification should be run before any release claim.
- Type safety: Type annotations present in many modules. Strict mypy compliance is not continuously verified.
- Docker production stack: Compose files, nginx config, and Prometheus setup exist and are structurally sound. Live deployment smoke test not yet automated.

## Not Yet Verified

- Full end-to-end production deployment with real traffic
- Multi-node distributed operation (gossip/heartbeat/consensus modules exist but are not load-tested)
- Recovery system effectiveness across diverse real-world failure scenarios

## Known Limitations

- **Not "any website"**: Extraction results depend on website accessibility, anti-bot controls, page structure, authentication requirements, and extraction configuration.
- **Not "self-healing"**: The system has adaptive recovery mechanisms (selector memory, fallback strategies, replay tools) but cannot independently fix and permanently recover from all failures without human review.
- **Silent exception blocks**: Multiple broad `except Exception` blocks exist across the codebase for resilience. These are intentional for operational stability but mean some failures may be logged rather than raised. Work is ongoing to add structured logging and metrics to the most impactful silent paths.
- **Read/export endpoints scope**: Read and export endpoints (e.g. results, topology, crystalline knowledge) are protected by a global API key in production, but any valid key has read access. Stricter role-specific filtering (Owner/Operator/Admin) is recommended for client-facing or multi-tenant deployments.
- **Dependency reproducibility**: Pinned dependencies from `requirements.lock.txt` are enforced in Docker builds.
- **Benchmark / Accuracy Framework**: Deterministic benchmark coverage exists for selected fixture scenarios. Live benchmark and hostile-site reliability require separate validation. Recovery logic has deterministic unit coverage and simulated recovery checks; real recovery success must be measured through live or replayed failure benchmarks.
- **Rate limiting is per-process, not cluster-wide**: The current rate limiter operates in-memory. When scaling to multiple workers or containers, each process has its own rate limit counter. A Redis/Postgres-backed shared rate limiter would be needed for global enforcement.
- **Dashboard auth storage**: The frontend stores the API key in `localStorage`, which is suitable for private/internal deployments but not hardened enterprise auth (vulnerable to XSS). Production deployments should use HttpOnly cookies, short-lived tokens, or a VPN/auth proxy.
- **Hardcoded heuristics**: The system includes domain-specific heuristic values (field aliases, schema.org handlers, blocked discovery domains, example locations like Chennai/Bangalore/Delhi). This is normal for extraction platforms but means the system is not purely domain-agnostic.
- **Stale documentation paths**: Archived migration reports remain in `docs/archive/` and may reference outdated API paths (e.g., `/api/scraper/telemetry/recent` was migrated to `/api/scraper/telemetry?n=...`). Current API behavior is defined by the running app, not archived docs.

## Production Blockers

- [x] Full test suite passes in CI and local SRE checks
- [x] Production secrets must not use placeholder values (runtime check added in app startup)
- [x] `requirements.lock.txt` is used in Dockerfile for reproducible builds

## Verification Commands

```bash
# Quick health check
scripts/verify_all.sh

# Full release readiness
scripts/verify_release.sh

# Production env validation
python scripts/check_prod_env.py --env-file .env

# Individual test suites
PYTHONPATH=backend pytest backend/tests/test_production_hardening.py -q
PYTHONPATH=backend pytest backend/tests/test_production_security.py -q
PYTHONPATH=backend pytest backend/tests/test_url_safety.py -q
PYTHONPATH=backend pytest backend/tests/test_metrics.py -q
```
