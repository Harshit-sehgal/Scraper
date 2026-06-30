"""IP Quality Scoring (Anti 28) - Track per-IP health and select the best IPs.

Responsible for:
- Per-IP success/failure/block metrics
- Quality scoring (0.0-1.0) per IP
- Top-N IP selection and bad-IP eviction
- Optional SQLite persistence of quality state
- Integration with :mod:`app.proxy_manager` for domain-aware proxy selection
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────
_DEFAULT_EVICTION_THRESHOLD = 0.1
_DEFAULT_DECAY_HALF_LIFE_HOURS = 6  # successes decay over time
_DB_LOCK = threading.Lock()
_DB_INITIALIZED: set[Path] = set()


def _db_path() -> Path:
    """Resolve the IP quality database path from settings (or default)."""
    if settings.STATE_FILE_PATH_DYNAMIC:
        base = Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()
    else:
        base = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"
    return base.parent / "ip_quality.db"


def _db_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (or create) the IP quality database with WAL mode."""
    path = db_path or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    if path not in _DB_INITIALIZED:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ip_quality (
                ip              TEXT PRIMARY KEY,
                success_count   INTEGER NOT NULL DEFAULT 0,
                failure_count   INTEGER NOT NULL DEFAULT 0,
                block_count     INTEGER NOT NULL DEFAULT 0,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                last_seen       REAL NOT NULL,
                last_latency_ms REAL,
                domain          TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ip_quality_last_seen
            ON ip_quality(last_seen)
            """
        )
        conn.commit()
        _DB_INITIALIZED.add(path)
    return conn


# ── Scoring Helpers ────────────────────────────────────────────────────


def _decay_factor(last_seen: float, half_life_hours: float | None = None) -> float:
    """Compute an exponential decay factor for success counts.

    Older successes count less toward the quality score so a proxy that
    was excellent last week but keeps failing now doesn't appear healthy.
    """
    half_life = half_life_hours or _DEFAULT_DECAY_HALF_LIFE_HOURS
    if half_life <= 0:
        return 1.0
    age_hours = (time.time() - last_seen) / 3600.0
    return 2.0 ** (-age_hours / half_life)


def _compute_quality_score(
    successes: int,
    failures: int,
    blocks: int,
    consecutive_failures: int,
    last_seen: float,
    *,
    half_life_hours: float | None = None,
) -> float:
    """Return a quality score in [0.0, 1.0] for a given IP.

    The formula:
        raw = (decayed_successes) / (decayed_successes + total_negatives + 1)
    heavily penalized by block count and consecutive failures.
    """
    decayed_success = successes * _decay_factor(last_seen, half_life_hours)
    total_negatives = failures + blocks * 3  # blocks are 3x worse than errors
    denominator = decayed_success + total_negatives + 1  # +1 avoids div by zero
    raw = decayed_success / denominator

    # Consecutive failure penalty: each consecutive failure reduces
    # the score multiplicatively.
    con_penalty = 0.5 ** consecutive_failures if consecutive_failures > 0 else 1.0

    return max(0.0, min(1.0, raw * con_penalty))


# ── IPQualityScorer ────────────────────────────────────────────────────


class IPQualityScorer:
    """In-memory per-IP quality tracker with optional SQLite persistence."""

    def __init__(self, *, persist: bool = True) -> None:
        self._lock = threading.Lock()
        self._persist = persist

        # ── in-memory state ────────────────────────────────────────
        # ip -> success_count
        self._successes: dict[str, int] = defaultdict(int)
        # ip -> failure_count
        self._failures: dict[str, int] = defaultdict(int)
        # ip -> block_count
        self._blocks: dict[str, int] = defaultdict(int)
        # ip -> consecutive_failure_count
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        # ip -> last_seen timestamp
        self._last_seen: dict[str, float] = {}
        # ip -> last recorded latency (ms)
        self._latencies: dict[str, float] = {}

        if self._persist:
            self._hydrate_from_db()

    # ── Public API ──────────────────────────────────────────────────

    def get_ip_score(self, ip: str) -> float:
        """Return the quality score (0.0-1.0) for *ip*.

        An IP with no history defaults to a neutral 0.5.
        """
        with self._lock:
            if ip not in self._last_seen:
                return 0.5  # neutral for new/unseen IPs
            return _compute_quality_score(
                self._successes.get(ip, 0),
                self._failures.get(ip, 0),
                self._blocks.get(ip, 0),
                self._consecutive_failures.get(ip, 0),
                self._last_seen.get(ip, time.time()),
            )

    def record_success(self, ip: str, latency_ms: float = 0.0) -> None:
        """Record a successful request via *ip*."""
        now = time.time()
        with self._lock:
            self._successes[ip] += 1
            self._consecutive_failures[ip] = 0
            self._last_seen[ip] = now
            if latency_ms > 0:
                self._latencies[ip] = latency_ms
            if self._persist:
                self._upsert(ip, now)

    def record_failure(self, ip: str) -> None:
        """Record a failed (non-block) request via *ip*."""
        now = time.time()
        with self._lock:
            self._failures[ip] += 1
            self._consecutive_failures[ip] += 1
            self._last_seen[ip] = now
            if self._persist:
                self._upsert(ip, now)

    def record_block(self, ip: str) -> None:
        """Record that *ip* was blocked (bot-detected)."""
        now = time.time()
        with self._lock:
            self._blocks[ip] += 1
            self._consecutive_failures[ip] += 3  # blocks heavily penalize
            self._last_seen[ip] = now
            if self._persist:
                self._upsert(ip, now)

    def get_best_ips(self, n: int = 5) -> list[str]:
        """Return the top *n* IPs by quality score (descending)."""
        with self._lock:
            scored: list[tuple[float, str]] = []
            for ip in self._last_seen:
                score = _compute_quality_score(
                    self._successes.get(ip, 0),
                    self._failures.get(ip, 0),
                    self._blocks.get(ip, 0),
                    self._consecutive_failures.get(ip, 0),
                    self._last_seen[ip],
                )
                scored.append((score, ip))
            scored.sort(key=lambda x: -x[0])
            return [ip for _, ip in scored[:n]]

    def evict_bad_ips(self, threshold: float | None = None) -> list[str]:
        """Remove IPs whose quality score is below *threshold*.

        Default threshold is 0.1.  Returns the list of evicted IPs.
        """
        thresh = threshold if threshold is not None else _DEFAULT_EVICTION_THRESHOLD
        evicted: list[str] = []
        with self._lock:
            to_evict: list[str] = []
            for ip in list(self._last_seen):
                score = _compute_quality_score(
                    self._successes.get(ip, 0),
                    self._failures.get(ip, 0),
                    self._blocks.get(ip, 0),
                    self._consecutive_failures.get(ip, 0),
                    self._last_seen[ip],
                )
                if score < thresh:
                    to_evict.append(ip)

            for ip in to_evict:
                self._remove_ip(ip)
                evicted.append(ip)

        if evicted and self._persist:
            self._delete_from_db(evicted)

        return evicted

    def get_all_scores(self) -> dict[str, float]:
        """Return ``{ip: score}`` for every known IP."""
        with self._lock:
            result: dict[str, float] = {}
            for ip in self._last_seen:
                result[ip] = _compute_quality_score(
                    self._successes.get(ip, 0),
                    self._failures.get(ip, 0),
                    self._blocks.get(ip, 0),
                    self._consecutive_failures.get(ip, 0),
                    self._last_seen[ip],
                )
            return result

    # ── Internal Helpers ────────────────────────────────────────────

    def _remove_ip(self, ip: str) -> None:
        """Clear all tracking data for *ip*. Must hold ``_lock``."""
        self._successes.pop(ip, None)
        self._failures.pop(ip, None)
        self._blocks.pop(ip, None)
        self._consecutive_failures.pop(ip, None)
        self._last_seen.pop(ip, None)
        self._latencies.pop(ip, None)

    def _upsert(self, ip: str, now: float) -> None:
        """Insert or update the IP row in SQLite.  Must hold ``_lock``."""
        if not self._persist:
            return
        try:
            with _DB_LOCK:
                conn = _db_conn()
                try:
                    conn.execute(
                        """
                        INSERT INTO ip_quality
                            (ip, success_count, failure_count, block_count,
                             consecutive_failures, last_seen, last_latency_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ip) DO UPDATE SET
                            success_count         = excluded.success_count,
                            failure_count         = excluded.failure_count,
                            block_count           = excluded.block_count,
                            consecutive_failures  = excluded.consecutive_failures,
                            last_seen             = excluded.last_seen,
                            last_latency_ms       = excluded.last_latency_ms
                        """,
                        (
                            ip,
                            self._successes.get(ip, 0),
                            self._failures.get(ip, 0),
                            self._blocks.get(ip, 0),
                            self._consecutive_failures.get(ip, 0),
                            now,
                            self._latencies.get(ip),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error:
            logger.debug("Failed to upsert IP quality for %s", ip, exc_info=True)

    def _hydrate_from_db(self) -> None:
        """Load persisted quality data into memory on startup."""
        try:
            with _DB_LOCK:
                conn = _db_conn()
                try:
                    rows = conn.execute(
                        "SELECT ip, success_count, failure_count, block_count, "
                        "consecutive_failures, last_seen, last_latency_ms "
                        "FROM ip_quality"
                    ).fetchall()
                finally:
                    conn.close()
            for row in rows:
                ip, suc, fail, blk, cons, seen, lat = row
                self._successes[ip] = suc
                self._failures[ip] = fail
                self._blocks[ip] = blk
                self._consecutive_failures[ip] = cons
                self._last_seen[ip] = seen
                if lat is not None:
                    self._latencies[ip] = lat
            if rows:
                logger.info("Hydrated IP quality state for %d IPs", len(rows))
        except sqlite3.Error:
            logger.warning("Failed to hydrate IP quality from DB", exc_info=True)

    def _delete_from_db(self, ips: list[str]) -> None:
        """Remove evicted IPs from SQLite."""
        if not ips:
            return
        try:
            with _DB_LOCK:
                conn = _db_conn()
                try:
                    conn.executemany("DELETE FROM ip_quality WHERE ip = ?", [(ip,) for ip in ips])
                    conn.commit()
                finally:
                    conn.close()
            logger.debug("Deleted %d evicted IPs from DB", len(ips))
        except sqlite3.Error:
            logger.debug("Failed to delete evicted IPs from DB", exc_info=True)


# ── Global Singleton ───────────────────────────────────────────────────

_scorer: IPQualityScorer | None = None
_scorer_lock = threading.Lock()


def get_ip_quality_scorer(*, persist: bool = True) -> IPQualityScorer:
    """Get or create the global IPQualityScorer singleton."""
    global _scorer
    if _scorer is not None:
        return _scorer
    with _scorer_lock:
        if _scorer is None:
            _scorer = IPQualityScorer(persist=persist)
    return _scorer


# ── Proxy Manager Integration ──────────────────────────────────────────


def get_best_proxy_for_domain(domain: str, n: int = 5) -> str | None:
    """Get the best available proxy for *domain* using IP quality scoring.

    Combines :func:`get_ip_quality_scorer().get_best_ips` with
    :class:`~app.proxy_manager.ProxyManager` domain-aware selection.
    """
    from app.proxy_manager import get_proxy_manager

    pm = get_proxy_manager()
    if not pm.enabled:
        return None

    scorer = get_ip_quality_scorer()
    best_ips = scorer.get_best_ips(n=n)

    # Prefer an IP that both has a high quality score and isn't blocked
    # for the requested domain.
    for candidate_ip in best_ips:
        proxy_url = pm.get_best_proxy(domain=domain)
        if proxy_url and candidate_ip in proxy_url:
            return proxy_url
        # The proxy_manager doesn't expose individual IPs directly, but
        # the quality scorer tracks IPs that correspond to proxy URLs.
        # First try the domain-aware best proxy from proxy_manager.
        fallback = pm.get_best_proxy(domain=domain)
        if fallback:
            # If the fallback URL contains a scored IP, prefer it.
            for ip in best_ips:
                if ip in fallback:
                    return fallback
            return fallback

    return pm.current_proxy
