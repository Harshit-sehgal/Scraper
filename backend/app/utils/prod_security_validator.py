"""Production Security Validator.

Enforces that required production credentials are not weak, placeholder, or default.
Raises ValueError on any validation failure to prevent application startup.
"""

from __future__ import annotations

import logging
import os
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


def validate_production_credentials(settings) -> None:
    """Validate that API keys and database password are secure in production.

    Raises ValueError if any credential does not meet production strength criteria.
    """
    if settings.ENV.lower() != "production":
        return

    logger.info("Running production security credential checks (hard startup gates)...")

    # 1. API Keys Validation
    keys_to_check = [
        ("DATAFORGE_API_KEY", settings.API_KEY),
        ("DATAFORGE_OPERATOR_API_KEY", settings.OPERATOR_API_KEY),
        ("DATAFORGE_ADMIN_API_KEY", settings.ADMIN_API_KEY),
    ]

    for name, value in keys_to_check:
        val = (value or "").strip()
        if not val:
            raise ValueError(
                f"Production check failed: {name} is empty or not configured. "
                f"In production mode, all key roles must be secured."
            )
        if val.lower() in WEAK_CREDENTIAL_PLACEHOLDERS:
            raise ValueError(
                f"Production check failed: {name} is set to a weak/placeholder value. "
                f"Please generate a strong random key."
            )
        if len(val) < 16:
            raise ValueError(
                f"Production check failed: {name} is too short ({len(val)} chars). "
                f"Must be at least 16 characters in production."
            )

    # 2. Database Password Validation (only if Storage Backend is Postgres)
    storage_backend = getattr(settings, "STORAGE_BACKEND", "").strip().lower() or os.environ.get("DATAFORGE_STORAGE_BACKEND", "sqlite").strip().lower()
    if storage_backend == "postgres":
        # Resolve database URL
        env_url = os.environ.get("DATAFORGE_DATABASE_URL", "").strip()
        db_url = env_url or getattr(settings, "DATABASE_URL", "") or ""
        if not db_url:
            raise ValueError(
                "Production check failed: STORAGE_BACKEND is set to postgres but "
                "DATAFORGE_DATABASE_URL is not configured."
            )

        try:
            parsed = urlsplit(db_url)
            password = parsed.password
        except Exception as e:
            raise ValueError(f"Production check failed: DATAFORGE_DATABASE_URL is not parseable: {e}")

        if not password:
            raise ValueError(
                "Production check failed: DATAFORGE_DATABASE_URL does not contain a password. "
                "A strong database password is required."
            )

        password = password.strip()
        if password.lower() in WEAK_CREDENTIAL_PLACEHOLDERS:
            raise ValueError(
                "Production check failed: DATAFORGE_DATABASE_URL password is set to a weak/placeholder value. "
                "Please configure a strong, unique database password."
            )

        if len(password) < 8:
            raise ValueError(
                f"Production check failed: DATAFORGE_DATABASE_URL password is too short ({len(password)} chars). "
                f"Must be at least 8 characters in production."
            )

    logger.info("Production security credential validation: ALL PASS")
