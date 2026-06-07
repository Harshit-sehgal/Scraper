#!/usr/bin/env python3
"""
Production Environment Configuration Generator.

This script dynamically generates a production environment file with strong,
unique, randomly generated cryptographic keys and passwords, preventing default
placeholders from leaking into deployment.
"""

import os
import secrets
import sys

TARGET_FILE = ".env.production"


def generate_strong_secret(length: int = 32) -> str:
    return secrets.token_hex(length)


def generate_strong_password(length: int = 16) -> str:
    return secrets.token_urlsafe(length)


def main():
    print("=" * 60)
    print("DataForge Production Environment Configuration Generator")
    print("=" * 60)

    if os.path.exists(TARGET_FILE):
        print(f"[WARNING] '{TARGET_FILE}' already exists on disk.")
        choice = input("Do you want to overwrite it with new generated secrets? (y/N): ").strip().lower()
        if choice != "y":
            print("Aborted. No changes were made.")
            sys.exit(0)

    print("\nGenerating strong random secrets...")
    api_key = generate_strong_secret()
    operator_key = generate_strong_secret()
    admin_key = generate_strong_secret()
    metrics_token = generate_strong_secret()
    db_password = generate_strong_password()
    grafana_password = generate_strong_password()

    config_content = f"""# DataForge Production Environment Configuration
# Generated automatically by scripts/generate_prod_env.py

# Central environment indicator
DATAFORGE_ENV=production

# Core API credentials (strong random keys)
DATAFORGE_API_KEY={api_key}
DATAFORGE_OPERATOR_API_KEY={operator_key}
DATAFORGE_ADMIN_API_KEY={admin_key}

# Metrics scrape token for Prometheus scraping
DATAFORGE_METRICS_TOKEN={metrics_token}

# CORS configuration (restrict to your production domain)
DATAFORGE_CORS_ORIGINS=["https://yourdomain.com"]

# Storage and Queue backend selection
DATAFORGE_STORAGE_BACKEND=postgres
DATAFORGE_QUEUE_BACKEND=postgres
DATAFORGE_WORKER_QUEUE=true

# Postgres Database configuration
DATAFORGE_DB_PASSWORD={db_password}
DATAFORGE_DATABASE_URL=postgresql://dataforge:{db_password}@postgres:5432/dataforge

# Infrastructure passwords
GRAFANA_PASSWORD={grafana_password}
"""

    try:
        # Create the file with mode 0o600 atomically. Setting the
        # umask before ``open`` closes the small window during which
        # the file existed with the user's default umask (typically
        # 0644, which would make plaintext production secrets
        # world-readable on a shared host). A concurrent process
        # could otherwise ``open()`` the file between the ``open``
        # and the ``os.chmod`` in the original implementation.
        # ``os.open`` with ``O_CREAT|O_WRONLY|O_TRUNC`` applies the
        # mode at inode-creation time, before any data is written.
        fd = os.open(
            TARGET_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(config_content)
        except Exception:
            # If the write itself fails, close and unlink the
            # half-written file so we don't leave a 0o600 stub
            # with a misleading ``.env.production`` next to it.
            try:
                os.unlink(TARGET_FILE)
            except OSError:
                pass
            raise
        print(f"\n[SUCCESS] Secure production configuration successfully written to '{TARGET_FILE}'.")
        print("          File permissions set to owner read/write only (chmod 600).")
        print("          Remember: Keep this file secure and NEVER commit it to Git.")
    except Exception as e:
        print(f"\n[ERROR] Failed to write '{TARGET_FILE}': {e}")
        sys.exit(1)

    print("\nNext Actions:")
    print(f"1. Open '{TARGET_FILE}' and replace 'https://yourdomain.com' with your actual production domain.")
    print("2. Run the environment validator to verify your newly generated configuration:")
    print(f"   python3 scripts/check_prod_env.py --env-file {TARGET_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
