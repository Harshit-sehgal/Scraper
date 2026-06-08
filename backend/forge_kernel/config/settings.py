"""Kernel settings — grouped configuration for the product kernel.

Uses pydantic-settings with focused groups rather than one giant object.
"""

from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SETTINGS_ENV_FILE = os.getenv("DATAFORGE_DOTENV_PATH", ".env").strip() or ".env"


class BrowserSettings(BaseSettings):
    """Playwright / browser configuration."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    PLAYWRIGHT_TIMEOUT: int = 45000
    PLAYWRIGHT_HEADLESS: bool = True
    BROWSER_VIEWPORT_WIDTH: int = 1280
    BROWSER_VIEWPORT_HEIGHT: int = 900
    BROWSER_MAX_CONTEXTS: int = 10
    PAGE_SETTLE_DELAY: float = 2.0
    PLAYWRIGHT_STEALTH: bool = True


class HttpSettings(BaseSettings):
    """HTTP fetching configuration."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    REQUEST_TIMEOUT: int = 20
    MAX_RETRIES: int = 2
    HTTP_BACKOFF_FACTOR: float = 0.5
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


class ExtractionSettings(BaseSettings):
    """Extraction pipeline configuration."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    PER_URL_TIMEOUT_SECONDS: int = 120
    MAX_RECORDS_PER_SOURCE: int = 25
    DEFAULT_MIN_RECORD_SCORE: float = 0.35
    AI_STRUCTURING_CHUNK_SIZE: int = 15
    SCORE_GATE_THRESHOLD_FACTOR: float = 0.5
    SCORE_GATE_ABSOLUTE_MIN: float = 0.1
    MAX_RECOVERY_ATTEMPTS: int = 3
    RECOVERY_TIMEOUT_MULTIPLIER: int = 4


class SecuritySettings(BaseSettings):
    """Security configuration — CORS, API keys, rate limiting, SSRF."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    ENV: str = "development"
    API_KEY: str = ""
    OPERATOR_API_KEY: str = ""
    ADMIN_API_KEY: str = ""
    METRICS_TOKEN: str = ""
    ALLOWED_INTERNAL_HOSTS: str = ""
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
    RATE_LIMIT_GLOBAL: str = "600/minute"
    RATE_LIMIT_JOB_CREATE: str = "10/minute"


class StorageSettings(BaseSettings):
    """Storage and queue configuration."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    STATE_FILE_PATH: str = ""
    AUDIT_LOG_DIR: str = ""
    MAX_JOB_HISTORY: int = 300
    MAX_RECYCLE_BIN_HISTORY: int = 300
    JOB_RESULTS_DISK_OFFLOAD_THRESHOLD: int = 1000

    @property
    def STORAGE_BACKEND(self) -> str:
        return (os.environ.get("DATAFORGE_STORAGE_BACKEND") or "sqlite").strip().lower()

    @property
    def DATABASE_URL(self) -> str:
        return (os.environ.get("DATAFORGE_DATABASE_URL") or "").strip()

    @property
    def QUEUE_BACKEND(self) -> str:
        return (os.environ.get("DATAFORGE_QUEUE_BACKEND") or "sqlite").strip().lower()


class OpsSettings(BaseSettings):
    """Operations and metrics configuration."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    METRICS_ENABLE_HISTOGRAMS: bool = True
    SMOKE_TEST_MODE: bool = False
    NODE_ID: str = "node-1"


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    LLM_TIMEOUT: int = 45
    LLM_FAST_TIMEOUT: int = 12
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_ATTEMPTS: int = 2
    LLM_ENABLE_PUBLIC_FALLBACKS: bool = False
    GROQ_API_ENDPOINT: str = "https://api.groq.com/openai/v1/chat/completions"

    @property
    def GROQ_API_KEY(self) -> str:
        return (os.environ.get("GROQ_API_KEY") or "").strip()


class KernelSettings(BaseSettings):
    """Aggregated kernel settings — wraps focused setting groups."""

    model_config = SettingsConfigDict(env_prefix="DATAFORGE_", env_file=_SETTINGS_ENV_FILE, extra="ignore")

    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    http: HttpSettings = Field(default_factory=HttpSettings)
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    ops: OpsSettings = Field(default_factory=OpsSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
