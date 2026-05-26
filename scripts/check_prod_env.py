#!/usr/bin/env python3
"""
Production Environment Check — DataForge Scraper.

Validates that the `.env` file has all required variables set correctly
before running `docker compose up`.

Usage:
    python scripts/check_prod_env.py [--env-file .env]

Exit codes:
    0 — All checks passed
    1 — One or more checks failed
"""

import argparse
import json
import sys
from pathlib import Path


REQUIRED_VARS = [
    "DATAFORGE_API_KEY",
    "DATAFORGE_CORS_ORIGINS",
    "DATAFORGE_DB_PASSWORD",
    "DATAFORGE_STORAGE_BACKEND",
    "DATAFORGE_DATABASE_URL",
    "DATAFORGE_WORKER_QUEUE",
    "DATAFORGE_ENV",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate production environment variables for DataForge Scraper."
    )
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
            value = value.strip().strip("\"'")
            env[key] = value
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
        else:
            print(f"  [INFO]  {name} is not set (optional).")
            return True

    if validator:
        if not validator(value):
            print(f"  [FAIL]  {name} = {value!r} failed validation.")
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
    return value


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
            "  [FAIL]  DATAFORGE_CORS_ORIGINS contains wildcard '*'. "
            "In production, CORS must be locked down to trusted domains."
        )
        return False

    for origin in origins:
        if not isinstance(origin, str) or not origin.startswith(("http://", "https://")):
            print(
                f"  [FAIL]  CORS origin {origin!r} is invalid. "
                "Must be a valid URL starting with http:// or https://."
            )
            return False

    return True


def check_storage_backend(value: str) -> bool:
    """Validate DATAFORGE_STORAGE_BACKEND is 'postgres'."""
    if value.lower() != "postgres":
        print(
            f"  [FAIL]  DATAFORGE_STORAGE_BACKEND={value!r}. "
            "Production requires 'postgres'."
        )
        return False
    return True


def check_worker_queue(value: str) -> bool:
    """Validate DATAFORGE_WORKER_QUEUE is 'true'."""
    if value.lower() not in ("true", "1", "yes"):
        print(
            f"  [FAIL]  DATAFORGE_WORKER_QUEUE={value!r}. "
            "Production requires 'true'."
        )
        return False
    return True


def check_queue_backend(value: str) -> bool:
    """Validate DATAFORGE_QUEUE_BACKEND is 'postgres'."""
    if value.lower() != "postgres":
        print(
            f"  [FAIL]  DATAFORGE_QUEUE_BACKEND={value!r}. "
            "Production requires 'postgres'."
        )
        return False
    return True


def check_grafana_password(value: str) -> bool:
    """Validate GRAFANA_PASSWORD is not a default/placeholder value."""
    default_values = {
        "admin",
        "password",
        "grafana",
        "change-me",
        "change-me-to-a-strong-password",
    }
    if value.lower() in default_values:
        print(
            f"  [FAIL]  GRAFANA_PASSWORD={_mask_value('GRAFANA_PASSWORD', value)} "
            "is a known default/placeholder value. "
            "Set a strong, unique Grafana admin password."
        )
        return False
    if len(value) < 8:
        print(
            f"  [FAIL]  GRAFANA_PASSWORD is too short ({len(value)} chars). "
            "Must be at least 8 characters."
        )
        return False
    return True


def check_database_url(value: str) -> bool:
    """Validate DATAFORGE_DATABASE_URL is a postgresql:// URL."""
    if not value.startswith(("postgresql://", "postgres://")):
        print(
            f"  [FAIL]  DATAFORGE_DATABASE_URL={value!r}. "
            "Must be a postgresql:// or postgres:// URL."
        )
        return False
    return True


def check_api_key(value: str) -> bool:
    """Validate DATAFORGE_API_KEY is not a default/placeholder value."""
    default_values = {
        "change-me",
        "change-me-to-a-random-secret",
        "dev-key",
        "test-key",
        "your-api-key-here",
    }
    if value.lower() in default_values:
        print(
            f"  [FAIL]  DATAFORGE_API_KEY={_mask_value('DATAFORGE_API_KEY', value)} "
            "is a known default/placeholder value. "
            "Generate a strong random key with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
        return False
    if len(value) < 16:
        print(
            f"  [FAIL]  DATAFORGE_API_KEY is too short ({len(value)} chars). "
            "Must be at least 16 characters."
        )
        return False
    return True


def check_db_password(value: str) -> bool:
    """Validate DATAFORGE_DB_PASSWORD is not a default/placeholder value."""
    default_values = {
        "dataforge",
        "change-me",
        "change-me-to-a-strong-password",
        "password",
        "postgres",
    }
    if value.lower() in default_values:
        print(
            f"  [FAIL]  DATAFORGE_DB_PASSWORD={_mask_value('DATAFORGE_DB_PASSWORD', value)} "
            "is a known default/placeholder value. "
            "Use a strong, unique password."
        )
        return False
    if len(value) < 8:
        print(
            f"  [FAIL]  DATAFORGE_DB_PASSWORD is too short ({len(value)} chars). "
            "Must be at least 8 characters."
        )
        return False
    return True


def check_env(value: str) -> bool:
    """Validate DATAFORGE_ENV is set to 'production'."""
    if value.lower() != "production":
        print(
            f"  [FAIL]  DATAFORGE_ENV={value!r}. "
            "Must be set to 'production'."
        )
        return False
    return True


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file).expanduser().resolve()
    print("DataForge Production Environment Check")
    print(f"  Env file: {env_path}")
    print()

    env = load_env_file(env_path)

    all_pass = True

    # ── Required vars ────────────────────────────────────────────────
    checks = [
        ("DATAFORGE_API_KEY", True, check_api_key,
         "Generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\""),
        ("DATAFORGE_CORS_ORIGINS", True, check_cors_origins,
         "Must be a JSON array of origins, e.g. [\"https://yourdomain.com\"]"),
        ("DATAFORGE_DB_PASSWORD", True, check_db_password,
         "Must match POSTGRES_PASSWORD in docker-compose.prod.yml"),
        ("DATAFORGE_STORAGE_BACKEND", True, check_storage_backend,
         "Must be 'postgres' for production"),
        ("DATAFORGE_DATABASE_URL", True, check_database_url,
         "Must be a postgresql:// URL matching docker-compose.prod.yml"),
        ("DATAFORGE_WORKER_QUEUE", True, check_worker_queue,
         "Must be 'true' for production"),
        ("DATAFORGE_QUEUE_BACKEND", True, check_queue_backend,
         "Must be 'postgres' for production — set DATAFORGE_QUEUE_BACKEND=postgres"),
        ("DATAFORGE_ENV", True, check_env,
         "Must be set to 'production'"),
    ]

    # ── Optional but recommended ─────────────────────────────────────────
    recommended = [
        ("GRAFANA_PASSWORD", False, check_grafana_password,
         "Set a strong Grafana admin password (reject: admin, password, grafana, change-me)"),
    ]

    for name, required, validator, hint in recommended:
        passed = check_var(env, name, required=required, validator=validator, hint=hint)
        if not passed:
            all_pass = False

    for name, required, validator, hint in checks:
        passed = check_var(env, name, required=required, validator=validator, hint=hint)
        if not passed:
            all_pass = False

    # ── Summary ──────────────────────────────────────────────────────
    print()
    if all_pass:
        print("Result: ALL CHECKS PASSED — environment is ready for production.")
        return 0
    else:
        print("Result: ONE OR MORE CHECKS FAILED — fix the issues above before deploying.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
