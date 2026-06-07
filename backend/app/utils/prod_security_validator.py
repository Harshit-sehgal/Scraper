"""Production Security Validator.

Enforces that required production credentials are not weak, placeholder, or default.
Raises ValueError on any validation failure to prevent application startup.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# Know placeholders or default values
WEAK_CREDENTIAL_PLACEHOLDERS = {
    "dataforge",
    "postgres",
    "password",
    "admin",
    "grafana",
    "change-me",
    "change-me-to-a-strong-password",
    "change-this-to-a-strong-password",
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


def _normalize_secret(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _is_weak_or_placeholder(value: str) -> bool:
    normalized = _normalize_secret(value)
    return (
        normalized in WEAK_CREDENTIAL_PLACEHOLDERS
        or normalized.startswith(PLACEHOLDER_PREFIXES)
        or any(fragment in normalized for fragment in PLACEHOLDER_FRAGMENTS)
    )


def _validate_distinct_api_keys(keys_to_check: list[tuple[str, str]]) -> None:
    seen: dict[str, str] = {}
    for name, value in keys_to_check:
        val = (value or "").strip()
        if not val:
            continue
        previous = seen.get(val)
        if previous:
            msg = (
                f"Production check failed: {name} reuses the same secret as {previous}. "
                "Production user, operator, and admin API keys must be distinct."
            )
            raise ValueError(
                msg,
            )
        seen[val] = name


def validate_production_credentials(settings) -> None:
    """Validate that API keys and database password are secure in production.

    Raises ValueError if any credential does not meet production strength criteria.
    Also runs in staging so misconfigurations are caught before promotion.
    """
    env = settings.ENV.lower()
    if env not in ("production", "staging"):
        return

    logger.info("Running %s security credential checks (hard startup gates)...", env)

    # 1. API Keys Validation
    keys_to_check = [
        ("DATAFORGE_API_KEY", settings.API_KEY),
        ("DATAFORGE_OPERATOR_API_KEY", settings.OPERATOR_API_KEY),
        ("DATAFORGE_ADMIN_API_KEY", settings.ADMIN_API_KEY),
    ]
    # 2. METRICS_TOKEN: optional in dev, mandatory in production/staging
    # when the /metrics endpoint is exposed.
    if getattr(settings, "METRICS_TOKEN", ""):
        keys_to_check.append(
            ("DATAFORGE_METRICS_TOKEN", settings.METRICS_TOKEN),
        )

    for name, value in keys_to_check:
        val = (value or "").strip()
        if not val:
            msg = (
                f"Production check failed: {name} is empty or not configured. In production mode, all key roles must be secured."
            )
            raise ValueError(
                msg,
            )
        if _is_weak_or_placeholder(val):
            msg = f"Production check failed: {name} is set to a weak/placeholder value. Please generate a strong random key."
            raise ValueError(
                msg,
            )
        if len(val) < 16:
            msg = (
                f"Production check failed: {name} is too short ({len(val)} chars). Must be at least 16 characters in production."
            )
            raise ValueError(
                msg,
            )

    _validate_distinct_api_keys(keys_to_check)

    # 2. Database Password Validation (only if Storage Backend is Postgres)
    storage_backend = settings.STORAGE_BACKEND
    if storage_backend == "postgres":
        # Resolve database URL
        db_url = settings.DATABASE_URL
        if not db_url:
            msg = "Production check failed: STORAGE_BACKEND is set to postgres but DATAFORGE_DATABASE_URL is not configured."
            raise ValueError(
                msg,
            )

        try:
            parsed = urlsplit(db_url)
            password = parsed.password
        except Exception as e:
            msg = f"Production check failed: DATAFORGE_DATABASE_URL is not parseable: {e}"
            raise ValueError(msg) from e

        if not password:
            msg = (
                "Production check failed: DATAFORGE_DATABASE_URL does not contain a password. "
                "A strong database password is required."
            )
            raise ValueError(
                msg,
            )

        password = password.strip()
        if _is_weak_or_placeholder(password):
            msg = (
                "Production check failed: DATAFORGE_DATABASE_URL password is set to a weak/placeholder value. "
                "Please configure a strong, unique database password."
            )
            raise ValueError(
                msg,
            )

        if len(password) < 8:
            msg = (
                "Production check failed: DATAFORGE_DATABASE_URL password is too short "
                f"({len(password)} chars). Must be at least 8 characters in production."
            )
            raise ValueError(
                msg,
            )

    logger.info("Production security credential validation: ALL PASS")
