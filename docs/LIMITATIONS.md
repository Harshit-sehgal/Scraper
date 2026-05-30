# Known Limitations

## Extraction Accuracy

- Benchmarks use **simplified HTML fixtures**, not real websites. Real-world accuracy depends on page structure consistency and schema accuracy.
- No golden dataset with real-world websites exists for validation.
- Recovery benchmarks use simulated metrics, not real failure injection.

## Anti-Bot & Site Compatibility

- The scraper does not work on every website.
- Extraction quality depends on site structure, rendering behavior, authentication, anti-bot controls, rate limits, and schema quality.
- The project is **not** a complete anti-bot solution.
- Advanced anti-bot scenarios (Cloudflare, DataDome, etc.) are not fully validated.

## Production Readiness

- Production readiness is not proven until the production stack is validated end to end.
- Postgres support exists but needs real CI/service validation before it can be relied upon in production.
- No load testing has been performed.
- No disaster recovery or backup/restore procedures are documented.

## Dashboard

- Dashboard auth is suitable for private/internal use only, **not** hostile shared browsers.
- Dashboard API key is stored in `localStorage` (insecure for shared machines).
- Dashboard telemetry is polled, not streamed (no WebSocket/SSE).
- Dashboard relies on CDN scripts (Chart.js, Tailwind) that require relaxed CSP.

## Security

- Rate limiting is single-process only (not distributed — bypassed by multi-instance deployment).
- Application SSRF checks should be backed by network-level egress controls.
- No audit logging for authentication events or admin actions.
- API keys are long-lived (no expiration or rotation mechanism).

## Testing & Benchmarks

- 54 of 1,712 tests skip due to missing external dependencies (Postgres, API keys).
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
