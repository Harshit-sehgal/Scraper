# Limitations

- The scraper does not work on every website.
- Extraction quality depends on site structure, rendering behavior, authentication, anti-bot controls, rate limits, and schema quality.
- The project is not a complete anti-bot solution.
- Production readiness is not proven until the production stack is validated end to end.
- Postgres support exists but needs real CI/service validation.
- Dashboard auth is suitable for private/internal use, not hostile shared browsers.
- Dashboard telemetry is polled, not streamed.
- Some adaptive/semantic components are experimental or weakly validated.
- Manual benchmark scripts are not pytest-collected.
- Docker dependency installation is not fully lock-file based.
- In-process rate limiting is not distributed.
- Application SSRF checks should be backed by network-level controls.
