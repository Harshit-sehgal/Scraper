#!/usr/bin/env python3
"""Standalone verification of P0 startup safety checks.

This script simulates what the pytest tests do:
- Set production env with dev auth enabled → verify RuntimeError
- Set production env with empty session secret → verify RuntimeError
"""

import os
import sys

# Set PYTHONPATH to backend
sys.path.insert(0, "backend")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")


def test_startup_blocks_dev_auth():
    """Simulate production with dev auth enabled. Should raise RuntimeError."""
    os.environ["DATAFORGE_ENV"] = "production"
    os.environ["DATAFORGE_ALLOW_INSECURE_DEV_AUTH"] = "true"
    os.environ["DATAFORGE_SESSION_SECRET"] = "valid-secret-for-test"
    os.environ["DATAFORGE_ADMIN_API_KEY"] = "admin-key-test"
    os.environ["DATAFORGE_API_KEY"] = "user-key-test"

    from app.config import settings
    from app.main import create_app

    # Force re-read of the overridden env vars
    settings.model_config["env_file"] = None

    try:
        # Monkey-patch the settings for this test
        with open("/dev/null", "w") as _:
            old_env = settings.ENV
            old_auth = settings.ALLOW_INSECURE_DEV_AUTH
            settings.ENV = "production"
            settings.ALLOW_INSECURE_DEV_AUTH = True
            try:
                create_app()
                return False
            except RuntimeError as e:
                return "ALLOW_INSECURE_DEV_AUTH" in str(e)
            finally:
                settings.ENV = old_env
                settings.ALLOW_INSECURE_DEV_AUTH = old_auth
    except Exception:
        return False


def test_startup_blocks_missing_secret():
    """Simulate production with empty session secret. Should raise RuntimeError."""
    from app.config import settings
    from app.main import create_app

    try:
        old_env = settings.ENV
        old_secret = settings.SESSION_SECRET
        old_auth = settings.ALLOW_INSECURE_DEV_AUTH
        settings.ENV = "production"
        settings.SESSION_SECRET = ""
        settings.ALLOW_INSECURE_DEV_AUTH = False
        try:
            create_app()
            return False
        except RuntimeError as e:
            return "SESSION_SECRET" in str(e)
        finally:
            settings.ENV = old_env
            settings.SESSION_SECRET = old_secret
            settings.ALLOW_INSECURE_DEV_AUTH = old_auth
    except Exception:
        return False


if __name__ == "__main__":
    ok1 = test_startup_blocks_dev_auth()
    ok2 = test_startup_blocks_missing_secret()
    if ok1 and ok2:
        pass
    else:
        sys.exit(1)
