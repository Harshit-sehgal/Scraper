"""Paths, observability, research, and federation configuration."""

import os

from pydantic_settings import BaseSettings


class PathSettings(BaseSettings):
    """File paths, observability, research, and federation settings."""

    # ─── Paths ─────────────────────────────────────────────────────────
    # F-DRIFT-001: STATE_DIR is the base directory for all mutable runtime
    # state. In the hardened Docker production profile, this is set to
    # /app/backend/data/w (a :rw sub-mount) so the parent /app/backend/data
    # is mounted :ro, preventing a compromised process from tampering with
    # ML/learning state files (semantic_state.json, selector_memory.json,
    # domain_intelligence.json, etc.) that live outside the writable
    # subdirectory.  In dev and non-hardened environments the default is
    # "" (empty), which means individual path defaults are used unchanged.
    STATE_DIR: str = ""

    SEMANTIC_STATE_PATH: str = "data/semantic_state.json"
    STATE_FILE_PATH: str = ""
    """Override for jobs_state.json path. Empty = use default ./backend/data/jobs_state.json"""
    AUDIT_LOG_DIR: str = ""
    """Override for audit log directory. Empty = use audit logger default."""
    DOMAIN_INTELLIGENCE_PATH: str = "data/domain_intelligence.json"
    SELECTOR_MEMORY_PATH: str = "data/selector_memory.json"
    SELECTOR_PROFILES_DIR: str = "profiles"
    """Directory for selector profile definitions."""

    # ─── Observability ─────────────────────────────────────────────────
    TELEMETRY_STREAM_MAXLEN: int = 1000
    TELEMETRY_RECORD_EXTRACTION: bool = True
    """Emit per-URL scrape telemetry events."""

    # ─── Semantic World State ──────────────────────────────────────────
    MOTIF_MIN_COOCCURRENCE: int = 2

    # ─── Domain Intelligence ───────────────────────────────────────────
    DOMAIN_INTELLIGENCE_SMOOTHING_ALPHA: float = 0.3

    # ─── Gossip Propagation ─────────────────────────────────────────────
    GOSSIP_PROPAGATION_INTERVAL: int = 60

    # ─── Federation / Sharding ─────────────────────────────────────────
    NODE_ID: str = "node-1"
    """Unique identifier for this node / worker context."""
    SHARD_ID: str = "shard-1"
    """Unique identifier for the sharded workload context."""

    # ─── Feature Flags ─────────────────────────────────────────────────
    ENABLE_EXPERIMENTAL_ROUTES: bool = False
    """Enable experimental / research-only API routes."""

    # ─── Rate Limiter Background Pruning ────────────────────────────────
    RATE_LIMIT_PRUNE_INTERVAL: int = 3600
    """Seconds between background prunes of the ``rate_limits`` table.
    Default 3600 (1 hour). Set to 0 to disable the background cron;
    the middleware's request-time pruning (every 300s) still runs.
    """

    # ─── Binary Download Hardening (FU-2026-07-04) ──────────────────────
    MAX_BINARY_DOWNLOAD_BYTES: int = 50 * 1024 * 1024
    """Maximum bytes a single ``download_binary`` call may stream from a
    remote URL. Defends against OOM/disk-exhaust via attacker-supplied
    URLs (the inbound ``MAX_BODY_SIZE`` middleware cap does not apply to
    server-initiated fetches). Defaults to 50 MB.
    """
    MAX_HTML_FETCH_BYTES: int = 25 * 1024 * 1024
    """Maximum bytes the HTML fetcher ('_extract_httpx_body') will accept
    from an upstream response. Prevents a single hostile page from
    materializing gigabytes of HTML into worker memory. Defaults to 25 MB.
    """

    # ─── Workflow Storage ───────────────────────────────────────────────
    WORKFLOW_BACKEND: str = "json"
    """CAND-P1-WORKFLOW-STORAGE-001: workflow storage backend.
    'json' (default) uses the existing JSONFileStore; 'sqlite' and
    'postgres' use the workflows table from storage_migrations.py.
    Can be overridden at runtime via DATAFORGE_WORKFLOW_BACKEND.

    .. deprecated::
        'json' is the dev default and must NOT be used in production.
        The production security validator will reject WORKFLOW_BACKEND='json'
        when DATAFORGE_ENV=production.  Use 'sqlite' or 'postgres' instead.
    """

    @property
    def DATA_DIR(self) -> str:
        """Resolve the base data directory for mutable runtime state.

        F-DRIFT-001: In the hardened Docker production profile, the
        operator sets ``DATAFORGE_STATE_DIR=/app/backend/data/w`` so that
        mutable runtime state (databases, JSON stores, results) lands in
        the ``:rw`` sub-mount while the rest of ``/app/backend/data`` is
        read-only.  When empty (the default), the original ``data/``
        layout is used for backward compatibility.

        This property also checks the raw ``DATAFORGE_STATE_DIR`` env var
        so that it can be set without going through Pydantic validation
        (useful in Docker Compose where env vars are set at container
        start).
        """
        return os.environ.get("DATAFORGE_STATE_DIR") or self.STATE_DIR or "data"
