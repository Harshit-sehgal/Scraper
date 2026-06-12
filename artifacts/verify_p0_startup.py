#!/usr/bin/env python3
"""Standalone verification of P0 startup safety checks.

This script simulates what the pytest tests do:
- Set production env with dev auth enabled → verify RuntimeError
- Set production env with empty session secret → verify RuntimeError
"""

import sys
import os

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
                print("FAIL: create_app() did not raise RuntimeError for dev auth")
                return False
            except RuntimeError as e:
                if "ALLOW_INSECURE_DEV_AUTH" in str(e):
                    print("PASS: Dev auth check raises RuntimeError")
                    return True
                else:
                    print(f"FAIL: Wrong error message: {e}")
                    return False
            finally:
                settings.ENV = old_env
                settings.ALLOW_INSECURE_DEV_AUTH = old_auth
    except Exception as e:
        print(f"FAIL: Unexpected exception: {e}")
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
            print("FAIL: create_app() did not raise RuntimeError for missing secret")
            return False
        except RuntimeError as e:
            if "SESSION_SECRET" in str(e):
                print("PASS: Session secret check raises RuntimeError")
                return True
            else:
                print(f"FAIL: Wrong error message: {e}")
                return False
        finally:
            settings.ENV = old_env
            settings.SESSION_SECRET = old_secret
            settings.ALLOW_INSECURE_DEV_AUTH = old_auth
    except Exception as e:
        print(f"FAIL: Unexpected exception: {e}")
        return False


if __name__ == "__main__":
    print("Running P0 startup checks...")
    print()
    ok1 = test_startup_blocks_dev_auth()
    print()
    ok2 = test_startup_blocks_missing_secret()
    print()
    if ok1 and ok2:
        print("All checks PASSED.")
    else:
        print("Some checks FAILED.")
        sys.exit(1)
