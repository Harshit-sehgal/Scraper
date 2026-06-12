# DataForge Validation

This project now has one local validation entry point:

```bash
python3 scripts/validate_local.py --quick
```

Use this before non-trivial edits. It sets safe test defaults, applies
timeouts to every subprocess, redacts secrets from logs, and writes
evidence under `artifacts/validation/`.

## Environment Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
npm ci
```

The current workspace has `python3`, not `python`. In CI, GitHub
Actions provides `python`, but local commands in this checkout should
use `python3` unless a virtual environment supplies `python`.

The validation runner sets these safe defaults for test runs:

```bash
DATAFORGE_DOTENV_PATH=/dev/null
DATAFORGE_ENV=test
DATAFORGE_STORAGE_BACKEND=sqlite
DATAFORGE_API_KEY=user-key
DATAFORGE_OPERATOR_API_KEY=operator-key
DATAFORGE_ADMIN_API_KEY=admin-key
DATAFORGE_SESSION_SECRET=test-session-secret-change-me
DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false
DATAFORGE_SKIP_DB_CHECK=true
PYTHONPATH=backend
```

## Commands

Quick validation:

```bash
python3 scripts/validate_local.py --quick
```

Full validation:

```bash
python3 scripts/validate_local.py --full
```

Backend-only validation:

```bash
python3 scripts/validate_local.py --backend
```

Frontend-only validation:

```bash
python3 scripts/validate_local.py --frontend
```

Security-oriented validation:

```bash
python3 scripts/validate_local.py --security
```

JSON output:

```bash
python3 scripts/validate_local.py --quick --json
```

With `--json`, stdout is machine-readable JSON. Progress and the final
human summary lines are written to stderr so callers can safely redirect
and parse stdout.

Makefile shortcuts:

```bash
make validate
make validate-full
make validate-backend
make validate-frontend
make validate-security
```

## Stable Checks

The quick path is the stable first gate:

- Python, Node, npm, git metadata.
- Required repository paths.
- `compileall` for backend, scripts, and `architecture_validator.py`.
- Architecture validator.
- Research boundary check.
- Dependency bounds check.
- URL safety and research boundary smoke tests.
- Targeted P0 regression tests for auth, tenant isolation, billing,
  quota, and route authorization.

The full path adds:

- Full backend pytest suite.
- Ruff, pyflakes, and mypy.
- Bandit and pip-audit.
- Production example environment placeholder check.
- Frontend install, tests, and formatting/lint check.

## Experimental And Opt-In Checks

The default runner does not claim coverage for opt-in environments:

- Postgres integration tests requiring `--run-postgres`.
- Browser E2E tests requiring Playwright/browser setup.
- Live benchmark or network-dependent tests.
- Real production deployment checks, TLS, backups, restore drills,
  monitoring, alert delivery, and load tests.

Those checks must be run explicitly and recorded separately.

## Logs

Every run writes:

```text
artifacts/validation/latest_summary.md
artifacts/validation/latest_summary.json
artifacts/validation/commands/
artifacts/validation/runs/<timestamp>_<mode>/
```

`latest_summary.*` and `commands/` always describe the most recent
run. The `runs/` directory preserves earlier run evidence so a quick
pass does not erase a full failed run.

Each command log includes:

- command
- working directory
- start and end time
- duration
- exit code
- stdout and stderr
- timeout
- status
- redaction status

## Interpreting Results

Do not treat a failed full run as a validation-runner failure by
default. Inspect the specific command logs first.

Statuses:

- `passed`: command met its expected exit behavior.
- `failed`: command completed but did not meet its expected exit
  behavior.
- `timeout`: command exceeded its timeout.
- `not_installed`: a required executable or module was missing.
- `skipped`: a check was intentionally skipped.

The production example environment check is expected to fail because
the example file contains placeholders. The runner treats that
non-zero exit as a pass for the check itself, but it is not production
readiness evidence.

## Current Truth

Use `docs/AGENT_TRUTH.md` and `artifacts/validation/latest_summary.md`
for current command evidence. Treat older status docs and historical
audit plans as stale unless their claims reproduce in the current
checkout.
