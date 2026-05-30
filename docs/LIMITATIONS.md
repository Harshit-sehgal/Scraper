# Known Limitations

## Extraction Accuracy

- Benchmarks use **simplified HTML fixtures**, not real websites. Real-world accuracy depends on page structure consistency and schema accuracy.
- A golden dataset skeleton exists at `backend/tests/golden_dataset/` with 5 stable scraping targets and F1-scoring tests. Run with `--run-golden-dataset` to begin populating real-world validation.
- Recovery benchmarks use simulated metrics, not real failure injection.

## Anti-Bot & Site Compatibility

- The scraper does not work on every website.
- Extraction quality depends on site structure, rendering behavior, authentication, anti-bot controls, rate limits, and schema quality.
- The project is **not** a complete anti-bot solution.
- Advanced anti-bot scenarios (Cloudflare, DataDome, etc.) are not fully validated.

## Production Readiness

- Production readiness is not proven until the production stack is validated end to end.
- Postgres support is CI-validated with a real Postgres service container. All Postgres tests pass (0 skipped).
- No load testing has been performed.
- No disaster recovery or backup/restore procedures are documented.

## Dashboard

- Dashboard auth is suitable for private/internal use only, **not** hostile shared browsers.
- Dashboard API key is stored in `localStorage` (insecure for shared machines).
- Dashboard telemetry is polled, not streamed (no WebSocket/SSE).
- Dashboard assets (Tailwind CSS, Chart.js) are **vendored locally** — strict `script-src 'self'` CSP is enforced.

## Security

- Rate limiting is single-process only (not distributed — bypassed by multi-instance deployment).
- Application SSRF checks should be backed by network-level egress controls.
- Audit logging is integrated into auth middleware (failures + non-GET mutations); RBAC, admin action, and data access logging integration pending in route handlers.
- API keys are long-lived (no expiration or rotation mechanism).

## Testing & Benchmarks

- ~54 of 1,884 tests skip due to missing external dependencies (Postgres, API keys).
- Manual benchmark scripts (`backend/benchmarks/`) are not collected by pytest.
- Code coverage percentage is not measured.
- Some adaptive/semantic components are experimental or weakly validated.

## Deployment

- Docker dependency installation is not fully lock-file based (uses `requirements.txt`, not `requirements.lock.txt`).
- Production startup validation exists but is only active when `DATAFORGE_ENV=production`.
- Nginx CORS allowlist must be customized for each deployment.

## Advanced Features

- Semantic/LLM extraction requires a GROQ_API_KEY and is optional.
- Selector learning, domain evolution, topology engine, and other advanced components exist but are unevenly tested.
- "Self-healing" and "autonomous adaptation" concepts are aspirational — not validated system behavior.
