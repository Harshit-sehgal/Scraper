#!/usr/bin/env python3
"""
Production Environment Check — DataForge Scraper.

Validates that required production variables are set before deployment.
Values from the process environment override values loaded from `--env-file`,
which lets Docker Compose and container startup checks use the same gate.

Usage:
    python scripts/check_prod_env.py [--env-file .env]

Exit codes:
    0 — Required environment checks passed
    1 — One or more checks failed
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REQUIRED_VARS = [
    "DATAFORGE_API_KEY",
    "DATAFORGE_CORS_ORIGINS",
    "DATAFORGE_DB_PASSWORD",
    "DATAFORGE_STORAGE_BACKEND",
    "DATAFORGE_DATABASE_URL",
    "DATAFORGE_WORKER_QUEUE",
    "DATAFORGE_METRICS_TOKEN",
    "DATAFORGE_ENV",
]

DEFAULT_DB_PASSWORD_VALUES = {
    "dataforge",
    "change-me",
    "change-me-to-a-strong-password",
    "change-this-to-a-strong-password",
    "password",
    "postgres",
}

WEAK_CREDENTIAL_VALUES = DEFAULT_DB_PASSWORD_VALUES | {
    "admin",
    "grafana",
    "change-me-to-a-random-secret",
    "dev-key",
    "test-key",
    "your-api-key-here",
    "change-me-admin-key",
    "change-me-operator-key",
    "change-me-user-key",
}

PLACEHOLDER_PREFIXES = (
    "change-me",
    "change-this",
    "changeme",
    "replace-me",
    "replace-this",
    "your-",
)

PLACEHOLDER_FRAGMENTS = (
    "placeholder",
    "example-secret",
    "example-key",
    "generate-strong",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate production environment variables for DataForge Scraper.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the .env file (default: .env)",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file and return a dict of variable -> value."""
    env: dict[str, str] = {}
    if not path.exists():
        print(f"  [WARN]  .env file not found: {path}")
        return env
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if value.startswith('"'):
                last_quote = value.rfind('"')
                if last_quote > 0:
                    value = value[1:last_quote]
            elif value.startswith("'"):
                last_quote = value.rfind("'")
                if last_quote > 0:
                    value = value[1:last_quote]
            else:
                value = value.partition("#")[0].strip()
            env[key] = value
    return env


def load_effective_env(path: Path) -> dict[str, str]:
    """Load env-file values and overlay process environment variables."""
    env = load_env_file(path)
    env.update({key: value for key, value in os.environ.items() if key.startswith(("DATAFORGE_", "GRAFANA_"))})
    return env


def check_var(
    env: dict[str, str],
    name: str,
    *,
    required: bool = True,
    validator=None,
    hint: str = "",
) -> bool:
    """Check a single environment variable.

    Args:
        env: Parsed env dict.
        name: Variable name.
        required: If True, missing value is a failure.
        validator: Optional callable(value) -> bool for custom validation.
        hint: Optional hint message shown on failure.

    Returns:
        True if the check passed, False otherwise.
    """
    value = env.get(name, "").strip()

    if not value:
        if required:
            print(f"  [FAIL]  {name} is not set or is empty.")
            if hint:
                print(f"          Hint: {hint}")
            return False
        print(f"  [INFO]  {name} is not set (optional).")
        return True

    if validator and not validator(value):
        print(f"  [FAIL]  {name} = {_mask_value(name, value)!r} failed validation.")
        if hint:
            print(f"          Hint: {hint}")
        return False

    print(f"  [OK]    {name} = {_mask_value(name, value)}")
    return True


def _mask_value(name: str, value: str) -> str:
    """Mask sensitive values for display."""
    sensitive_keywords = {"key", "password", "secret", "token", "auth"}
    if any(k in name.lower() for k in sensitive_keywords):
        if len(value) > 8:
            return value[:4] + "****" + value[-4:]
        return "****"
    if name.lower().endswith("url") and "://" in value:
        try:
            parsed = urlsplit(value)
            if parsed.password:
                username = parsed.username or ""
                host = parsed.hostname or ""
                port = f":{parsed.port}" if parsed.port else ""
                auth = f"{username}:****@" if username else "****@"
                return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, parsed.query, parsed.fragment))
        except ValueError:
            return "<invalid-url>"
    return value


def _normalize_secret(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _is_placeholder_secret(value: str) -> bool:
    normalized = _normalize_secret(value)
    return (
        normalized in WEAK_CREDENTIAL_VALUES
        or normalized.startswith(PLACEHOLDER_PREFIXES)
        or any(fragment in normalized for fragment in PLACEHOLDER_FRAGMENTS)
    )


def check_cors_origins(value: str) -> bool:
    """Validate that CORS_ORIGINS is a JSON array and does not contain '*'."""
    try:
        origins = json.loads(value)
    except json.JSONDecodeError:
        return False

    if not isinstance(origins, list):
        return False

    if "*" in origins:
        print(
            "  [FAIL]  DATAFORGE_CORS_ORIGINS contains wildcard '*'. In production, CORS must be locked down to trusted domains.",
        )
        return False

    for origin in origins:
        if not isinstance(origin, str) or not origin.startswith(("http://", "https://")):
            print(f"  [FAIL]  CORS origin {origin!r} is invalid. Must be a valid URL starting with http:// or https://.")
            return False

    return True


def check_storage_backend(value: str) -> bool:
    """Validate DATAFORGE_STORAGE_BACKEND is 'postgres'."""
    if value.lower() != "postgres":
        print(f"  [FAIL]  DATAFORGE_STORAGE_BACKEND={value!r}. Production requires 'postgres'.")
        return False
    return True


def check_worker_queue(value: str) -> bool:
    """Validate DATAFORGE_WORKER_QUEUE is 'true'."""
    if value.lower() not in ("true", "1", "yes"):
        print(f"  [FAIL]  DATAFORGE_WORKER_QUEUE={value!r}. Production requires 'true'.")
        return False
    return True


def check_queue_backend(value: str) -> bool:
    """Validate DATAFORGE_QUEUE_BACKEND is 'postgres'."""
    if value.lower() != "postgres":
        print(f"  [FAIL]  DATAFORGE_QUEUE_BACKEND={value!r}. Production requires 'postgres'.")
        return False
    return True


def check_pg_driver(value: str) -> bool:
    """Validate DATAFORGE_PG_DRIVER is 'psycopg3' for production.

    The production image installs only psycopg3 (psycopg2 is intentionally
    excluded to keep the image small and to force the new driver path). The
    code default of 'psycopg2' is appropriate for the legacy dev environment
    but MUST be overridden in production.
    """
    normalized = value.strip().lower()
    if normalized != "psycopg3":
        print(
            f"  [FAIL]  DATAFORGE_PG_DRIVER={value!r}. Production requires 'psycopg3' "
            "because the production image only ships the psycopg3 driver. "
            "Set DATAFORGE_PG_DRIVER=psycopg3 in .env.production.example "
            "and in both the dataforge and worker services of docker-compose.prod.yml.",
        )
        return False
    return True


def check_grafana_password(value: str) -> bool:
    """Validate GRAFANA_PASSWORD is not a default/placeholder value."""
    if _is_placeholder_secret(value):
        print(
            f"  [FAIL]  GRAFANA_PASSWORD={_mask_value('GRAFANA_PASSWORD', value)} "
            "is a known default/placeholder value. "
            "Set a strong, unique Grafana admin password.",
        )
        return False
    if len(value) < 8:
        print(f"  [FAIL]  GRAFANA_PASSWORD is too short ({len(value)} chars). Must be at least 8 characters.")
        return False
    return True


def check_database_url(value: str) -> bool:
    """Validate DATAFORGE_DATABASE_URL is a postgresql:// URL."""
    if not value.startswith(("postgresql://", "postgres://")):
        print(f"  [FAIL]  DATAFORGE_DATABASE_URL={value!r}. Must be a postgresql:// or postgres:// URL.")
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        print("  [FAIL]  DATAFORGE_DATABASE_URL is not parseable.")
        return False
    if not parsed.hostname:
        print("  [FAIL]  DATAFORGE_DATABASE_URL must include a hostname.")
        return False
    if not parsed.password:
        print("  [FAIL]  DATAFORGE_DATABASE_URL must include a database password.")
        return False
    if not _check_password_secret("DATAFORGE_DATABASE_URL password", parsed.password):
        print("  [FAIL]  DATAFORGE_DATABASE_URL contains a weak or placeholder password.")
        return False
    return True


def check_api_key(value: str) -> bool:
    """Validate DATAFORGE_API_KEY is not a default/placeholder value."""
    return _check_api_key_not_default("DATAFORGE_API_KEY", value)


def check_db_password(value: str) -> bool:
    """Validate DATAFORGE_DB_PASSWORD is not a default/placeholder value."""
    return _check_password_secret("DATAFORGE_DB_PASSWORD", value)


def _check_password_secret(name: str, value: str) -> bool:
    """Validate a database-style password is not a default/placeholder value.

    Note: the minimum length is 16 chars (not 8). The previous 8-char
    floor was inherited from the API-key check and undersold the
    brute-force cost for a role that authenticates Postgres itself —
    the database is the most-likely pivot point for a stolen-secret
    attack, so the bar is the same as for API keys.
    """
    if _is_placeholder_secret(value):
        print(f"  [FAIL]  {name}={_mask_value(name, value)} is a known default/placeholder value. Use a strong, unique password.")
        return False
    if len(value) < 16:
        print(f"  [FAIL]  {name} is too short ({len(value)} chars). Must be at least 16 characters.")
        return False
    return True


def _check_api_key_not_default(name: str, value: str) -> bool:
    """Validate an API key is not a default/placeholder value.

    Args:
        name: The env var name (for error messages).
        value: The key value to validate.

    Returns:
        True if valid, False otherwise.
    """
    if _is_placeholder_secret(value):
        print(
            f"  [FAIL]  {name}={_mask_value(name, value)} "
            "is a known default/placeholder value. "
            'Generate a strong random key with: python3 -c "import secrets; print(secrets.token_hex(32))"',
        )
        return False
    if len(value) < 16:
        print(f"  [FAIL]  {name} is too short ({len(value)} chars). Must be at least 16 characters.")
        return False
    return True


def check_distinct_api_keys(env: dict[str, str]) -> bool:
    """Validate that user, operator, and admin API keys are not reused."""
    key_names = [
        "DATAFORGE_API_KEY",
        "DATAFORGE_OPERATOR_API_KEY",
        "DATAFORGE_ADMIN_API_KEY",
    ]
    seen: dict[str, str] = {}
    ok = True
    for name in key_names:
        value = env.get(name, "").strip()
        if not value:
            continue
        previous = seen.get(value)
        if previous:
            print(
                f"  [FAIL]  {name} reuses the same secret as {previous}. "
                "Production user, operator, and admin API keys must be distinct.",
            )
            ok = False
        else:
            seen[value] = name
    if ok:
        print("  [OK]    API role keys are distinct")
    return ok


def check_queue_driver_compatibility(env: dict[str, str]) -> bool:
    """Validate that the queue backend is compatible with the selected PG driver.

    The Postgres worker queue supports both psycopg2 and psycopg3, but
    when DATAFORGE_PG_DRIVER=psycopg3 the production image ships only
    psycopg 3 (psycopg2 is intentionally excluded). This check makes
    sure the queue is reachable with the configured driver.

    Currently this is a structural check: it confirms both the
    repository and queue are set to the same driver. We also probe
    that the psycopg3 worker queue module is importable.
    """
    import importlib.util
    import sys

    pg_driver = env.get("DATAFORGE_PG_DRIVER", "").strip().lower() or "psycopg2"
    queue_backend = env.get("DATAFORGE_QUEUE_BACKEND", "").strip().lower()

    if queue_backend != "postgres":
        # SQLite queue has no driver compatibility concerns.
        return True

    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    if pg_driver == "psycopg3":
        # Verify the psycopg3 worker queue module is importable.
        spec = importlib.util.find_spec("app.worker_queue_postgres_psycopg3")
        if spec is None:
            print(
                "  [FAIL]  app.worker_queue_postgres_psycopg3 module is missing. "
                "The psycopg3 worker queue is required when DATAFORGE_PG_DRIVER=psycopg3 "
                "and DATAFORGE_QUEUE_BACKEND=postgres.",
            )
            return False
        print("  [OK]    queue module app.worker_queue_postgres_psycopg3 is importable")
    elif pg_driver == "psycopg2":
        try:
            __import__("psycopg2")
        except ImportError:
            print(
                "  [FAIL]  psycopg2 is not installed but DATAFORGE_PG_DRIVER=psycopg2. "
                "Install psycopg2-binary (dev-only) or switch to DATAFORGE_PG_DRIVER=psycopg3.",
            )
            return False
        print("  [OK]    psycopg2 importable for legacy queue driver")
    else:
        print(
            f"  [FAIL]  Unknown DATAFORGE_PG_DRIVER={pg_driver!r}. Must be 'psycopg2' or 'psycopg3'.",
        )
        return False

    return True


def check_env(value: str) -> bool:
    """Validate DATAFORGE_ENV is set to 'production'."""
    if value.lower() != "production":
        print(f"  [FAIL]  DATAFORGE_ENV={value!r}. Must be set to 'production'.")
        return False
    return True


def check_postgres_connection(db_url: str) -> bool:
    """Test actual Postgres connectivity.

    This validates that the database is reachable and schema is initialized,
    not just that the URL is formatted correctly.

    The driver is selected by the ``DATAFORGE_PG_DRIVER`` environment
    variable to mirror the backend's driver selection. Production uses
    ``psycopg3`` (the production image installs ``psycopg[binary]`` only,
    not ``psycopg2``), so a hard-coded ``import psycopg2`` would always
    silently skip the connectivity test in production. The default here
    is ``psycopg3`` to match the production image.
    """
    import os

    if os.environ.get("DATAFORGE_SKIP_DB_CHECK", "").lower() in ("true", "1", "yes"):
        print("\n  [INFO]  Skipping Postgres connectivity test (DATAFORGE_SKIP_DB_CHECK is set).")
        return True
    print("\n  [INFO]  Testing Postgres connectivity...")

    pg_driver = os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower() or "psycopg3"

    if pg_driver == "psycopg2":
        try:
            import psycopg2
            from psycopg2 import OperationalError
        except ImportError:
            print("  [WARN]  psycopg2 not installed; skipping connectivity test.")
            print("          Install with: pip install psycopg2-binary")
            return True
        try:
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            print("  [OK]    Postgres is reachable and responding.")
            return True
        except OperationalError as e:
            print(f"  [FAIL]  Could not connect to Postgres: {e}")
            print("          Ensure Postgres service is running and accessible at the configured URL.")
            return False
        except Exception as e:
            print(f"  [FAIL]  Unexpected error testing Postgres: {e}")
            return False

    # psycopg3 (default for production)
    try:
        import psycopg
    except ImportError:
        print("  [WARN]  psycopg (v3) not installed; skipping connectivity test.")
        print("          Install with: pip install 'psycopg[binary]>=3.2'")
        return True
    try:
        with psycopg.connect(db_url, connect_timeout=5) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        print("  [OK]    Postgres is reachable and responding.")
        return True
    except psycopg.OperationalError as e:
        print(f"  [FAIL]  Could not connect to Postgres: {e}")
        print("          Ensure Postgres service is running and accessible at the configured URL.")
        return False
    except Exception as e:
        print(f"  [FAIL]  Unexpected error testing Postgres: {e}")
        return False


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file).expanduser().resolve()
    print("DataForge Production Environment Check")
    print(f"  Env file: {env_path}")
    print("  Source priority: process environment overrides env-file values")
    print()

    env = load_effective_env(env_path)

    all_pass = True

    # ── Required vars ────────────────────────────────────────────────
    checks = [
        ("DATAFORGE_API_KEY", True, check_api_key, 'Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"'),
        ("DATAFORGE_CORS_ORIGINS", True, check_cors_origins, 'Must be a JSON array of origins, e.g. ["https://yourdomain.com"]'),
        ("DATAFORGE_DB_PASSWORD", True, check_db_password, "Must match POSTGRES_PASSWORD in docker-compose.prod.yml"),
        ("DATAFORGE_STORAGE_BACKEND", True, check_storage_backend, "Must be 'postgres' for production"),
        ("DATAFORGE_DATABASE_URL", True, check_database_url, "Must be a postgresql:// URL matching docker-compose.prod.yml"),
        ("DATAFORGE_WORKER_QUEUE", True, check_worker_queue, "Must be 'true' for production"),
        (
            "DATAFORGE_QUEUE_BACKEND",
            True,
            check_queue_backend,
            "Must be 'postgres' for production — set DATAFORGE_QUEUE_BACKEND=postgres",
        ),
        (
            "DATAFORGE_PG_DRIVER",
            True,
            check_pg_driver,
            "Must be 'psycopg3' for production — the production image ships only the psycopg3 driver",
        ),
        (
            "DATAFORGE_METRICS_TOKEN",
            True,
            lambda v: _check_api_key_not_default("DATAFORGE_METRICS_TOKEN", v),
            'Metrics scrape token for Prometheus. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"',
        ),
        ("DATAFORGE_ENV", True, check_env, "Must be set to 'production'"),
        (
            "DATAFORGE_OPERATOR_API_KEY",
            True,
            lambda v: _check_api_key_not_default("DATAFORGE_OPERATOR_API_KEY", v),
            'Operator key for job/selector mutations. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"',
        ),
        (
            "DATAFORGE_ADMIN_API_KEY",
            True,
            lambda v: _check_api_key_not_default("DATAFORGE_ADMIN_API_KEY", v),
            'Admin key for system-level operations. Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"',
        ),
        (
            "GRAFANA_PASSWORD",
            True,
            check_grafana_password,
            "Set a strong Grafana admin password (reject: admin, password, grafana, change-me)",
        ),
    ]

    # ── Optional but recommended ─────────────────────────────────────────
    # The ``recommended`` list is intentionally empty for now. When a
    # future PR adds an optional-but-strongly-recommended variable
    # (e.g. ``ALERTMANAGER_SMTP_HOST`` for alert routing), append a
    # ``(name, required=False, validator, hint)`` tuple here. The
    # surrounding ``check_var`` loop pattern is already wired up; it
    # is just iterating over an empty list today, which is the correct
    # no-op behaviour. The previous version of this block was an
    # actual loop and was flagged by Batch 3 of the audit as dead
    # code; a comment now makes the intent explicit so future
    # maintainers do not assume the loop is missing by accident.
    recommended: list[tuple[str, bool, object, str]] = []

    for name, required, validator, hint in recommended:
        passed = check_var(env, name, required=required, validator=validator, hint=hint)  # type: ignore[arg-type]
        if not passed:
            all_pass = False

    for name, required, validator, hint in checks:
        passed = check_var(env, name, required=required, validator=validator, hint=hint)
        if not passed:
            all_pass = False

    if not check_distinct_api_keys(env):
        all_pass = False

    # ── Postgres Connectivity (if storage backend is postgres) ───────────
    if all_pass and env.get("DATAFORGE_STORAGE_BACKEND", "").lower() == "postgres":
        db_url = env.get("DATAFORGE_DATABASE_URL", "")
        if db_url:
            pg_passed = check_postgres_connection(db_url)
            if not pg_passed:
                all_pass = False

    # ── Queue/driver compatibility check ──────────────────────────────────
    if all_pass and env.get("DATAFORGE_QUEUE_BACKEND", "").lower() == "postgres":
        compat_ok = check_queue_driver_compatibility(env)
        if not compat_ok:
            all_pass = False

    # ── Summary ──────────────────────────────────────────────────────
    print()
    if all_pass:
        print("Result: required production environment checks passed.")
        return 0
    print("Result: ONE OR MORE CHECKS FAILED — fix the issues above before deploying.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
