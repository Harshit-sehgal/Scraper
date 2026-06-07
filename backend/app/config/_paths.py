"""Paths, observability, research, and federation configuration."""

from pydantic_settings import BaseSettings


class PathSettings(BaseSettings):
    """File paths, observability, research, and federation settings."""

    # ─── Paths ─────────────────────────────────────────────────────────
    SEMANTIC_STATE_PATH: str = "data/semantic_state.json"
    STATE_FILE_PATH: str = ""
    """Override for jobs_state.json path. Empty = use default ./backend/data/jobs_state.json"""
    AUDIT_LOG_DIR: str = ""
    """Override for audit log directory. Empty = use audit logger default."""
    DOMAIN_INTELLIGENCE_PATH: str = "data/domain_intelligence.json"
    SELECTOR_MEMORY_PATH: str = "data/selector_memory.json"
    SELECTOR_DECAY_SNAPSHOT_PATH: str = "data/selector_decay_snapshots.json"
    REGRESSION_REGISTRY_PATH: str = "data/regression_registry.json"
    SELECTOR_PROFILES_DIR: str = "profiles"
    """Directory for selector profile definitions."""
    FRONTEND_DIR: str = ""
    """Override for frontend static files directory. Empty = auto-detect."""

    # ─── Observability ─────────────────────────────────────────────────
    TELEMETRY_STREAM_MAXLEN: int = 1000
    DRIFT_LOG_MAXLEN: int = 100
    HEATMAP_MAX_SCORE: float = 10.0
    HEATMAP_DECAY_RATE: float = 0.9
    TELEMETRY_RECORD_EXTRACTION: bool = True
    """Emit per-URL scrape telemetry events."""

    # ─── Semantic Pipeline Thresholds ──────────────────────────────────
    PIPELINE_INSTABILITY_THRESHOLD_MAX: float = 0.9
    PIPELINE_CONTRADICTION_PENALTY_MAX: float = 0.8
    PIPELINE_COHERENCE_THRESHOLD_MAX: float = 0.7
    PIPELINE_INSTABILITY_DELTA_MAX: float = 0.4
    PIPELINE_CONTRADICTION_DELTA_MAX: float = 0.6
    PIPELINE_TOPOLOGY_DELTA_MAX: float = 0.15

    # ─── Memory / GC ───────────────────────────────────────────────────
    RESOURCE_SHEDDING_MAX_BYTES: int = 10_000_000
    TOPOLOGY_MAX_REGIONS: int = 50
    MOTIF_PRUNE_THRESHOLD: float = 0.2

    # ─── Semantic World State ──────────────────────────────────────────
    MOTIF_MIN_COOCCURRENCE: int = 2
    REGRESSION_CAPTURE_SCORE_FACTOR: float = 0.5
    REGRESSION_LOW_QUALITY_CONFIDENCE: float = 0.6

    # ─── Domain Intelligence ───────────────────────────────────────────
    DOMAIN_INTELLIGENCE_SMOOTHING_ALPHA: float = 0.3

    # ─── Domain Health Alerts ──────────────────────────────────────────
    DOMAIN_HEALTH_ALERT_COOLDOWN: int = 60

    # ─── Gossip Propagation ────────────────────────────────────────────
    GOSSIP_PROPAGATION_INTERVAL: int = 60

    # ─── Federation / Sharding ─────────────────────────────────────────
    NODE_ID: str = "node-1"
    """Unique identifier for this node / worker context."""
    SHARD_ID: str = "shard-1"
    """Unique identifier for the sharded workload context."""

    # ─── Feature Flags ─────────────────────────────────────────────────
    ENABLE_EXPERIMENTAL_ROUTES: bool = False
    """Enable experimental / research-only API routes."""

    # ─── Rate Limiter Background Pruning ────────────────────────
    RATE_LIMIT_PRUNE_INTERVAL: int = 3600
    """Seconds between background prunes of the ``rate_limits`` table.
    Default 3600 (1 hour). Set to 0 to disable the background cron;
    the middleware's request-time pruning (every 300s) still runs.
    """
