#!/usr/bin/env python3
"""
Production Environment Configuration Generator.

This script dynamically generates a production environment file with strong,
unique, randomly generated cryptographic keys and passwords, preventing default
placeholders from leaking into deployment.
"""

import contextlib
import os
import secrets
import sys
from pathlib import Path

# Make ``scripts/_fsync_helper`` importable regardless of CWD.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _fsync_helper import write_text_sync

TARGET_FILE = ".env.production"
SECRET_DIR = ".secrets"


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
    session_secret = generate_strong_secret()
    metrics_token = generate_strong_secret()
    db_password = generate_strong_password()
    grafana_password = generate_strong_password()

    # The previous implementation hard-coded ``postgres:5432`` as
    # the database host. That is correct for a docker-compose.prod.yml
    # deploy but wrong for an external managed Postgres (RDS,
    # Cloud SQL, etc.). Ask the operator so the generated URL is
    # usable in the most common setups.
    default_db_host = "postgres:5432"
    db_host = input(f"Postgres host:port (default {default_db_host}): ").strip() or default_db_host
    # Strip any scheme prefix the operator might paste; the
    # generated DSN below always uses postgresql://.
    db_host = db_host.split("://", 1)[-1].strip("/")

    config_content = f"""# DataForge Production Environment Configuration
# Generated automatically by scripts/generate_prod_env.py

# Central environment indicator
DATAFORGE_ENV=production

# Core API/session credentials. These point to Docker-secret-compatible
# files generated next to this env file so the plaintext values do not
# appear in docker inspect environment output.
DATAFORGE_API_KEY_FILE=./.secrets/dataforge_api_key
DATAFORGE_OPERATOR_API_KEY_FILE=./.secrets/dataforge_operator_api_key
DATAFORGE_ADMIN_API_KEY_FILE=./.secrets/dataforge_admin_api_key
DATAFORGE_SESSION_SECRET_FILE=./.secrets/dataforge_session_secret

# Active billing provider (fill these provider values manually).
DODO_PAYMENTS_API_KEY=CHANGE_ME_DODO_LIVE_API_KEY
DODO_PAYMENTS_ENVIRONMENT=live_mode
DODO_PAYMENTS_WEBHOOK_KEY=CHANGE_ME_DODO_STANDARD_WEBHOOK_KEY
DODO_PRODUCT_ID_STARTER=CHANGE_ME_DODO_STARTER_PRODUCT_ID
DODO_PRODUCT_ID_PRO=CHANGE_ME_DODO_PRO_PRODUCT_ID
DODO_PRODUCT_ID_ENTERPRISE=CHANGE_ME_DODO_ENTERPRISE_PRODUCT_ID
DODO_CHECKOUT_RETURN_URL=https://yourdomain.com/app/?dodo_return=1

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
DATAFORGE_DATABASE_URL=postgresql://dataforge:{db_password}@{db_host}/dataforge

# Infrastructure passwords. Grafana also receives this via
# ./.secrets/grafana_admin_password in docker-compose.prod.yml.
GRAFANA_PASSWORD={grafana_password}

# -----------------------------------------------------------------------------
# ⚠️  ALERTMANAGER SECRETS — must be set manually (this script does NOT
#     generate them). Without these, alertmanager will start in a
#     degraded state and refuse to deliver email or Slack alerts.
#
#   ALERTMANAGER_SMTP_HOST=smtp.example.com:587
#   ALERTMANAGER_SMTP_USER=alerts@example.com
#   ALERTMANAGER_SMTP_PASS=...                 # never commit
#   ALERTMANAGER_EMAIL_FROM=alertmanager@example.com
#   ALERTMANAGER_EMAIL_TO=ops@example.com
#   ALERTMANAGER_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
#                                                  # never commit
#
#   For docker-compose.prod.yml, the SLACK_WEBHOOK_URL is also accepted
#   as a Docker secret at ./.secrets/slack_webhook so it never appears
#   in ``docker inspect`` env output.
# -----------------------------------------------------------------------------
"""

    try:
        os.makedirs(SECRET_DIR, mode=0o700, exist_ok=True)
        secret_files = {
            "dataforge_api_key": api_key,
            "dataforge_operator_api_key": operator_key,
            "dataforge_admin_api_key": admin_key,
            "dataforge_session_secret": session_secret,
            "pg_exporter_user": "dataforge",
            "pg_exporter_password": db_password,
            "grafana_admin_password": grafana_password,
            # Empty placeholder so docker compose can render; fill this
            # with a real webhook before relying on Slack delivery.
            "slack_webhook": "",
        }
        for filename, value in secret_files.items():
            secret_path = os.path.join(SECRET_DIR, filename)
            write_text_sync(secret_path, value, perm=0o600)

        # Create the file with mode 0o600 atomically. Setting the
        # umask before ``open`` closes the small window during which
        # the file existed with the user's default umask (typically
        # 0644, which would make plaintext production secrets
        # world-readable on a shared host). A concurrent process
        # could otherwise ``open()`` the file between the ``open``
        # and the ``os.chmod`` in the original implementation.
        # ``os.open`` with ``O_CREAT|O_WRONLY|O_TRUNC`` applies the
        # mode at inode-creation time, before any data is written.
        try:
            write_text_sync(TARGET_FILE, config_content, perm=0o600)
        except Exception:
            # If the write itself fails, clean up the half-written
            # file so we don't leave a 0o600 stub with a misleading
            # ``.env.production`` next to it.
            with contextlib.suppress(OSError):
                os.unlink(TARGET_FILE)
            raise
        print(f"\n[SUCCESS] Secure production configuration successfully written to '{TARGET_FILE}'.")
        print("          File permissions set to owner read/write only (chmod 600).")
        print(f"          Docker secret files written under '{SECRET_DIR}/' (chmod 600).")
        print("          Remember: Keep this file secure and NEVER commit it to Git.")
    except Exception as e:
        print(f"\n[ERROR] Failed to write '{TARGET_FILE}': {e}")
        sys.exit(1)

    print("\nNext Actions:")
    print(f"1. Open '{TARGET_FILE}' and replace 'https://yourdomain.com' with your actual production domain.")
    print("2. Set the ALERTMANAGER_* secrets listed at the bottom of the file")
    print("   (SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO,")
    print("   SLACK_WEBHOOK_URL). The generator does NOT create them because")
    print("   they are operator-specific (your mail relay, your Slack workspace).")
    print(f"   If you use Slack, write the webhook URL to {SECRET_DIR}/slack_webhook.")
    print("3. Run the environment validator to verify your newly generated configuration:")
    print(f"   python3 scripts/check_prod_env.py --env-file {TARGET_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
