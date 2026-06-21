"""File-backed AuthProfile store shared across worker processes.

Thin namespace over ``JSONFileStore`` so the auth-profile router
has a type name on disk distinct from other JSON-backed stores.
Compatibility with prior code is preserved: the public API
surface is unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.utils.json_file_store import JSONFileStore

DEFAULT_AUTH_PROFILES_FILENAME = "auth_profiles.json"
AUTH_PROFILES_ENV = "DATAFORGE_AUTH_PROFILES_FILE"


def default_auth_profiles_path() -> Path:
    """Resolve the on-disk path for the auth-profile store.

    Reads the env var on every call so tests can override it after
    import and operators can repoint the store without restarting
    running workers.
    """
    env_value = os.environ.get(AUTH_PROFILES_ENV, "").strip()
    if env_value:
        return Path(env_value)
    return Path(__file__).resolve().parents[2] / "data" / DEFAULT_AUTH_PROFILES_FILENAME


class AuthProfileStore(JSONFileStore):
    """File-backed AuthProfile registry.

    Same persistence and concurrency contract as
    ``JSONFileStore``: read-through on every read, flock-serialised
    atomic write per mutation. Persists to
    ``<repo>/data/auth_profiles.json`` by default; override via
    ``DATAFORGE_AUTH_PROFILES_FILE``.
    """

    def _default_path(self) -> Path:
        return default_auth_profiles_path()
