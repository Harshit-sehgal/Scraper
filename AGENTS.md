# Agent Instructions

This repository is DataForge Scraper, a pre-production FastAPI + Playwright web extraction platform for lawful, accessible-web extraction.

## Truth Source

- Start with `docs/AGENT_TRUTH.md`.
- Treat `PROJECT_STATUS.md`, `docs/CURRENT_STATUS.md`, old audit deliverables, roadmap files, and archived plans as historical unless their claims are reproduced by fresh commands in the current checkout.
- Use code and command output as source of truth. Do not claim a gate passed unless you ran it or can point to a current log artifact.

## Baseline First

Use Python 3.12. Before major edits, run the baseline gates with safe local settings:

```bash
export DATAFORGE_DOTENV_PATH=/dev/null
export DATAFORGE_ENV=test
export DATAFORGE_STORAGE_BACKEND=sqlite
export DATAFORGE_API_KEY=user-key
export DATAFORGE_OPERATOR_API_KEY=operator-key
export DATAFORGE_ADMIN_API_KEY=admin-key
export DATAFORGE_SESSION_SECRET=test-session-secret-change-me
export DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false
export DATAFORGE_SKIP_DB_CHECK=true
export PYTHONPATH=backend

python -m compileall -q backend scripts architecture_validator.py
python architecture_validator.py
python scripts/check_research_boundary.py
python scripts/validate_dependency_bounds.py
python -m pytest backend/tests/test_url_safety.py backend/tests/test_research_boundary.py -q
```

Record outputs under `artifacts/validation/` when doing validation work.

## P0 Safety Rules

- Add failing tests before changing P0 behavior.
- Keep authentication centralized through `app.utils.rbac.resolve_auth_context`.
- Enforce tenant isolation through explicit owner/org/project checks before returning jobs, results, events, exports, recycle-bin items, audit logs, or billing records.
- Misconfigured API auth must fail closed. `/api/*` routes are protected unless intentionally exempt.
- Preserve product safety: do not add CAPTCHA bypass, anti-bot bypass, paywall bypass, private-system scraping, login-protected scraping, or unauthorized access features.
- Do not edit experimental/research modules unless the task directly requires it.

## Production Claims

Do not call this project production-ready or 100/100 SaaS-ready unless staging deployment, TLS, secrets, backups, restore drill, monitoring, alerting, load tests, auth, tenant isolation, billing/usage enforcement, benchmark gates, and incident runbooks are proven in the current checkout and target environment.
