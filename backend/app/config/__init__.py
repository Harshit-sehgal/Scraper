"""Centralized Configuration for DataForge Scraper.

All hardcoded values, timeouts, thresholds, paths, and tunables
live here — not scattered across modules. Import via:

    from app.config import settings

To override, set the corresponding env var (e.g. PLAYWRIGHT_TIMEOUT=45000).

Settings are split by domain into mixin classes under ``app/config/``
and combined into a single ``Settings`` class via multi-inheritance.
"""

from __future__ import annotations

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config._browser import BrowserSettings
from app.config._communication import CommunicationSettings
from app.config._extraction import ExtractionSettings
from app.config._jobs import JobRunnerSettings
from app.config._paths import PathSettings
from app.config._security import SecuritySettings

_SETTINGS_ENV_FILE = os.getenv("DATAFORGE_DOTENV_PATH", ".env").strip() or ".env"


class _BaseCfg(BaseSettings):
    """Common base class providing the shared SettingsConfigDict.

    All mixin classes and the final Settings class inherit from this
    so that ``model_config`` is defined exactly once in the MRO.
    """

    model_config = SettingsConfigDict(
        env_prefix="DATAFORGE_",
        env_file=_SETTINGS_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class Settings(
    # Order matters: mixins with properties that reference other fields
    # should come before mixins that define those fields.
    BrowserSettings,
    CommunicationSettings,
    ExtractionSettings,
    SecuritySettings,
    JobRunnerSettings,
    PathSettings,
    _BaseCfg,
):
    """Combined application settings.

    This class inherits from all domain-specific mixin classes, each
    of which defines a group of related settings fields. Properties,
    ``__getattr__`` aliases, and the ``model_validator`` are defined
    here to avoid inheritance conflicts.

    Access via the module-level ``settings`` singleton:

        from app.config import settings
        settings.PLAYWRIGHT_TIMEOUT
    """

    # ─── Dynamic properties (read from env vars at runtime) ─────────────

    @property
    def GROQ_API_KEY(self) -> str:  # noqa: N802
        """Groq API key for LLM calls. Read from GROQ_API_KEY env var dynamically."""
        return (os.environ.get("GROQ_API_KEY") or "").strip()

    @property
    def WORKER_QUEUE(self) -> bool:  # noqa: N802
        """Whether worker queue mode is enabled. Read from DATAFORGE_WORKER_QUEUE env var dynamically."""
        return (os.environ.get("DATAFORGE_WORKER_QUEUE") or "").strip().lower() in ("1", "true", "yes")

    @property
    def SMOKE_TEST_MODE(self) -> bool:  # noqa: N802
        """Whether smoke test mode is enabled. Reads from DATAFORGE_SMOKE_TEST_MODE env var dynamically."""
        return (os.environ.get("DATAFORGE_SMOKE_TEST_MODE") or "").strip().lower() in ("true", "1", "yes")

    @property
    def STORAGE_BACKEND(self) -> str:  # noqa: N802
        """Storage backend. Reads from DATAFORGE_STORAGE_BACKEND env var dynamically. Default: 'sqlite'."""
        return (os.environ.get("DATAFORGE_STORAGE_BACKEND") or "sqlite").strip().lower()

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        """Database URL. Reads from DATAFORGE_DATABASE_URL env var dynamically."""
        return (os.environ.get("DATAFORGE_DATABASE_URL") or "").strip()

    @property
    def PG_MIN_CONN(self) -> int:  # noqa: N802
        """Postgres pool minimum size. Reads from DATAFORGE_PG_MIN_CONN."""
        raw = (os.environ.get("DATAFORGE_PG_MIN_CONN") or "1").strip()
        try:
            value = int(raw)
        except ValueError:
            return 1
        return max(1, min(value, 1000))

    @property
    def PG_MAX_CONN(self) -> int:  # noqa: N802
        """Postgres pool maximum size. Reads from DATAFORGE_PG_MAX_CONN."""
        raw = (os.environ.get("DATAFORGE_PG_MAX_CONN") or "10").strip()
        try:
            value = int(raw)
        except ValueError:
            return 10
        return max(1, min(value, 1000))

    @property
    def QUEUE_BACKEND_DYNAMIC(self) -> str:  # noqa: N802
        """Queue backend (dynamic). Reads from DATAFORGE_QUEUE_BACKEND env var dynamically."""
        return (os.environ.get("DATAFORGE_QUEUE_BACKEND") or self.QUEUE_BACKEND).strip().lower()

    @property
    def STATE_FILE(self) -> str:  # noqa: N802
        """State file path (legacy alias). Reads from DATAFORGE_STATE_FILE env var dynamically."""
        return (os.environ.get("DATAFORGE_STATE_FILE") or "").strip()

    @property
    def SEMANTIC_STATE_PATH_DYNAMIC(self) -> str:  # noqa: N802
        """Semantic state path (dynamic). Reads from SEMANTIC_STATE_PATH env var dynamically."""
        return os.environ.get("SEMANTIC_STATE_PATH") or self.SEMANTIC_STATE_PATH

    @property
    def STATE_FILE_PATH_DYNAMIC(self) -> str:  # noqa: N802
        """State file path (dynamic). Reads from DATAFORGE_STATE_FILE env var dynamically."""
        return os.environ.get("DATAFORGE_STATE_FILE") or self.STATE_FILE_PATH

    @property
    def TEST_SELECTOR_DECAY_PERSISTENCE(self) -> bool:  # noqa: N802
        """Whether to persist selector decay snapshots during tests."""
        return (os.environ.get("TEST_SELECTOR_DECAY_PERSISTENCE") or "").strip().lower() in ("true", "1", "yes")

    # ─── Backward-compatible aliases ────────────────────────────────────

    def __getattr__(self, name: str):
        """Provide backwards-compatible aliases for config parameters."""
        aliases = {
            "BROWSER_POOL_SIZE": "BROWSER_MAX_CONTEXTS",
            "RENDER_TIMEOUT": "PLAYWRIGHT_TIMEOUT",
            "FETCH_TIMEOUT": "REQUEST_TIMEOUT",
            "MIN_RECORD_SCORE": "DEFAULT_MIN_RECORD_SCORE",
        }
        if name in aliases:
            return super().__getattribute__(aliases[name])
        msg = f"'{type(self).__name__}' object has no attribute '{name}'"
        raise AttributeError(msg)

    # ─── Validators ────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _auto_promote_db_backed_rate_limit(self) -> Settings:
        """Promote ``RATE_LIMIT_DB_BACKED`` to True in production-like envs."""
        if self.ENV.lower() in {"production", "staging"} and "RATE_LIMIT_DB_BACKED" not in self.model_fields_set:
            self.RATE_LIMIT_DB_BACKED = True
        return self


settings = Settings()
