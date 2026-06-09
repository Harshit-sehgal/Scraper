"""API security, CORS, rate limiting, and authentication configuration."""

from pydantic_settings import BaseSettings


class SecuritySettings(BaseSettings):
    """API keys, CORS, rate limiting, CSP, and authentication settings."""

    ALLOWED_INTERNAL_HOSTS: str = ""
    """Comma-separated list of allowed internal hostnames (for testing / smoke)."""

    # ─── API Security ──────────────────────────────────────────────────
    ENV: str = "development"
    """Application runtime environment: development or production."""
    ALLOW_INSECURE_DEV_AUTH: bool = False
    """Require an explicit bypass flag for insecure local development auth."""
    API_KEY: str = ""
    """If set, all /api/* endpoints require X-API-Key header."""
    OPERATOR_API_KEY: str = ""
    """If set, operator routes require this key."""
    ADMIN_API_KEY: str = ""
    """If set, powerful admin routes require this key."""
    METRICS_TOKEN: str = ""
    """If set, /metrics endpoint requires Authorization: Bearer <token>."""
    ALERT_WEBHOOK_URL: str | None = None
    """URL to send webhook alerts for domain anti-bot level shifts."""
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
    """Allowed origins for CORS."""
    CSP_REPORT_ONLY: bool = True
    """Attach a report-only Content-Security-Policy header to every response."""

    # ─── Session Auth ───────────────────────────────────────────────────
    SESSION_SECRET: str = ""
    """Secret key for signing session cookies. Must be unique per deployment."""
    SESSION_MAX_AGE: int = 86400
    """Session cookie max age in seconds (default 24h)."""

    # ─── Metrics ───────────────────────────────────────────────────────
    METRICS_ENABLE_HISTOGRAMS: bool = True
    """Enable request duration and operation latency histograms in /metrics output."""
    METRICS_HISTOGRAM_BUCKETS: str = "0.01,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0,30.0,60.0,120.0"
    """Comma-separated bucket boundaries for duration histograms (seconds)."""

    # ─── Rate Limiting ─────────────────────────────────────────────────
    RATE_LIMIT_GLOBAL: str = "600/minute"
    """Aggregate rate limit across all clients for /api/* endpoints. Empty = disabled."""
    RATE_LIMIT_PER_IP: str = "100/minute"
    """Per-IP rate limit when per-IP tracking is enabled."""
    RATE_LIMIT_PER_IP_ENABLED: bool = True
    """Enable per-IP rate limiting."""
    RATE_LIMIT_JOB_CREATE: str = "10/minute"
    """Stricter rate limit for job creation (POST /api/jobs)."""
    RATE_LIMIT_DISCOVER: str = "20/minute"
    """Rate limit for discovery endpoint."""
    RATE_LIMIT_DB_BACKED: bool = False
    """Enable shared, database-backed rate limiting for multi-process environments."""
