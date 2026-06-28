"""Crawl Policy Engine — operational governance for the scraper.

Provides:
  - Per-domain concurrency budgets
  - Global concurrency cap
  - Request pacing (min delay between requests to same domain)
  - Retry ceilings per domain with cooldown
  - Best-effort robots.txt awareness
  - Domain reputation tracking
  - SQLite persistence for cooldown/failure state (survives restarts)

Usage:
    policy = get_crawl_policy()
    await policy.check_domain("example.com")
    # ... fetch ...
    policy.record_result("example.com", success=True)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)

# ── Domain state persistence (SQLite) ─────────────────────────────────
_POLICY_DB_LOCK = threading.Lock()
_POLICY_DB_INITIALIZED: set[Path] = set()


def _policy_db_path() -> Path:
    """Resolve the crawl-policy database path from settings."""
    if settings.STATE_FILE_PATH_DYNAMIC:
        base = Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()
    else:
        base = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"
    return base.parent / "crawl_policy_state.db"


def _policy_db_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (or create) the crawl-policy database with WAL mode."""
    path = db_path or _policy_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    if path not in _POLICY_DB_INITIALIZED:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_state (
                domain              TEXT PRIMARY KEY,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                total_fetches       INTEGER NOT NULL DEFAULT 0,
                last_fetch_time     REAL    NOT NULL DEFAULT 0,
                cooldown_until      REAL    NOT NULL DEFAULT 0,
                robots_disallowed   TEXT    NOT NULL DEFAULT '[]',
                crawl_delay         REAL    NOT NULL DEFAULT 0,
                robots_checked      INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
        _POLICY_DB_INITIALIZED.add(path)
    return conn


# ─── Domain State ───────────────────────────────────────────────────────


@dataclass
class DomainState:
    """Tracks operational state for a single domain."""

    domain: str
    active_fetches: int = 0
    consecutive_failures: int = 0
    total_fetches: int = 0
    last_fetch_time: float = 0.0
    cooldown_until: float = 0.0
    robots_disallowed: set[str] = field(default_factory=set)
    robots_checked: bool = False
    crawl_delay: float = 0.0  # robots.txt Crawl-Delay if specified


class CrawlPolicyEngine:
    """Governs domain-level crawling behaviour."""

    def __init__(self) -> None:
        self._domains: dict[str, DomainState] = defaultdict(lambda: DomainState(domain=""))
        self._robots_allowed: dict[str, set[str]] = defaultdict(set)  # domain -> Allow paths
        self._global_active_fetches = 0
        self._max_concurrency = settings.CRAWL_PER_DOMAIN_CONCURRENCY
        self._max_global_concurrency = settings.CRAWL_MAX_TOTAL_CONCURRENCY
        self._default_delay = settings.CRAWL_DEFAULT_DELAY_SECONDS
        self._max_retries = settings.CRAWL_MAX_RETRIES_PER_DOMAIN
        self._cooldown_seconds = settings.CRAWL_COOLDOWN_SECONDS
        self._max_cooldown_seconds = getattr(settings, "CRAWL_MAX_COOLDOWN_SECONDS", 3600)
        self._cooldown_multiplier = getattr(settings, "CRAWL_COOLDOWN_MULTIPLIER", 2.0)
        self._respect_robots = settings.CRAWL_RESPECT_ROBOTS
        self._max_pages_per_domain = settings.CRAWL_MAX_PAGES_PER_DOMAIN
        # Async lock to prevent race conditions on domain budget reservations.
        # See the "Reserve Domain Capacity" section in check_domain().
        self._reserve_lock = asyncio.Lock()
        # Thread lock for sync methods (record_result, get_domain_state, etc.)
        self._thread_lock = threading.Lock()
        # Hydrate domain state from SQLite on startup
        self._load_from_db()

    # ─── Public API ────────────────────────────────────────────────────

    async def check_domain(self, url: str) -> str | None:
        """Check whether a URL can be fetched under crawl policy.

        Returns:
            None if allowed, or an error message string if blocked.

        """
        domain = self._extract_domain(url)
        if not domain:
            return "Invalid URL"

        # Bypass checks for allowed internal hosts (e.g. nginx, localhost)
        allowed_hosts = {h.strip().lower() for h in settings.ALLOWED_INTERNAL_HOSTS.split(",") if h.strip()}
        allowed_hosts.update({"localhost", "127.0.0.1"})
        if domain in allowed_hosts:
            return None

        # Global concurrency check
        if self._global_active_fetches >= self._max_global_concurrency:
            return f"Global concurrency limit reached ({self._max_global_concurrency})"

        state = self._get_state(domain)

        # Cooldown check
        if time.time() < state.cooldown_until:
            remaining = int(state.cooldown_until - time.time())
            logger.info("Domain %s in cooldown for %ds (%d consecutive failures)", domain, remaining, state.consecutive_failures)
            return f"Domain {domain} in cooldown ({remaining}s remaining)"

        # Page budget check
        if state.total_fetches >= self._max_pages_per_domain:
            return f"Domain {domain} reached page budget ({self._max_pages_per_domain})"

        # Concurrency budget check
        if state.active_fetches >= self._max_concurrency:
            return f"Domain {domain} at max concurrency ({self._max_concurrency})"

        # Delay check
        elapsed = time.time() - state.last_fetch_time
        required_delay = max(state.crawl_delay, self._default_delay)
        if elapsed < required_delay:
            wait = required_delay - elapsed
            return f"Domain {domain} delay not met (wait {wait:.1f}s)"

        # robots.txt check (best-effort, cached)
        if self._respect_robots and not state.robots_checked:
            await self._check_robots_txt(domain)

        if self._respect_robots:
            path = self._extract_path(url)
            allowed_paths = self._robots_allowed.get(domain, set())
            if self._is_path_disallowed(path, state.robots_disallowed, allowed_paths):
                logger.info("robots.txt disallows %s on %s", path, domain)
                return f"robots.txt disallows {path} on {domain}"

        # ── Reserve Domain Capacity (under lock) ────────────────────────
        # The check-and-increment section must be atomic to prevent races:
        # without the lock, two concurrent tasks could both see capacity
        # available and both pass, exceeding the configured limits.
        async with self._reserve_lock:
            state = self._get_state(domain)

            # Re-check under lock — another task may have taken the slot
            if state.active_fetches >= self._max_concurrency:
                return f"Domain {domain} at max concurrency ({self._max_concurrency})"
            if self._global_active_fetches >= self._max_global_concurrency:
                return f"Global concurrency limit reached ({self._max_global_concurrency})"

            state.active_fetches += 1
            self._global_active_fetches += 1
            return None

    def record_result(self, url: str, success: bool) -> None:
        """Record the outcome of a fetch for a domain."""
        domain = self._extract_domain(url)
        if not domain:
            return

        with self._thread_lock:
            state = self._get_state(domain)
            state.active_fetches = max(0, state.active_fetches - 1)
            self._global_active_fetches = max(0, self._global_active_fetches - 1)
            state.last_fetch_time = time.time()
            state.total_fetches += 1

            if success:
                state.consecutive_failures = 0
            else:
                state.consecutive_failures += 1
                if state.consecutive_failures >= self._max_retries:
                    # Exponential backoff: each failure cycle doubles the cooldown,
                    # capped at max_cooldown_seconds. This prevents rapid re-queuing
                    # against a hard-blocked domain while still giving it a chance
                    # to recover.
                    cycle = state.consecutive_failures - self._max_retries + 1
                    cooldown = min(
                        self._cooldown_seconds * (self._cooldown_multiplier**cycle),
                        self._max_cooldown_seconds,
                    )
                    state.cooldown_until = time.time() + cooldown
                    logger.warning(
                        "Domain %s: %d consecutive failures, exponential cooldown %.0fs (cycle %d, max %ds)",
                        domain,
                        state.consecutive_failures,
                        cooldown,
                        cycle,
                        self._max_cooldown_seconds,
                    )

            # Persist key state to SQLite so cooldowns and failure counts
            # survive process restarts.
            self._persist_domain(domain, state)

    def get_domain_state(self, domain: str) -> dict | None:
        """Get the current state for a domain (for observability)."""
        state = self._domains.get(domain)
        if not state:
            return None
        return {
            "domain": state.domain,
            "active_fetches": state.active_fetches,
            "consecutive_failures": state.consecutive_failures,
            "total_fetches": state.total_fetches,
            "cooldown": max(0.0, state.cooldown_until - time.time()),
            "robots_checked": state.robots_checked,
        }

    def get_domain_health_score(self, domain: str) -> float:
        """Calculate a health score [0, 1] for a domain based on recent successes / failures."""
        state = self._domains.get(domain)
        if not state or state.total_fetches == 0:
            return 1.0

        # Linear penalty for consecutive failures
        failure_penalty = (state.consecutive_failures / self._max_retries) * 0.8

        # Simple success ratio component
        # Note: we don't track total successes explicitly, but we can infer it
        # for a better metric we might want to track windowed success rate

        score = 1.0 - failure_penalty
        if time.time() < state.cooldown_until:
            score *= 0.2  # Severely penalized if in cooldown

        return round(max(0.0, score), 2)

    def get_all_domain_states(self) -> dict[str, dict]:
        """Get states for all tracked domains."""
        states = {d: s for d in sorted(self._domains.keys()) if (s := self.get_domain_state(d))}
        # Add global summary
        states["_global"] = {
            "active_fetches": self._global_active_fetches,
            "max_concurrency": self._max_global_concurrency,
            "tracked_domains": len(self._domains),
        }
        return states

    def reset_domain(self, url_or_domain: str) -> None:
        """Reset a domain's state (e.g. after manual override).

        Removes state from both in-memory dict and SQLite.
        """
        domain = self._extract_domain(url_or_domain) or url_or_domain
        self._domains.pop(domain, None)
        # Also purge from SQLite so a restart doesn't re-hydrate stale state
        try:
            with _POLICY_DB_LOCK:
                conn = _policy_db_conn()
                try:
                    conn.execute("DELETE FROM domain_state WHERE domain = ?", (domain,))
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error:
            logger.warning("Failed to delete domain state for %s from SQLite", domain, exc_info=True)
        logger.info("Crawl policy: reset state for domain %s", domain)

    # ─── Internal Helpers ──────────────────────────────────────────────

    def _get_state(self, domain: str) -> DomainState:
        if domain not in self._domains:
            self._domains[domain] = DomainState(domain=domain)
        return self._domains[domain]

    def _load_from_db(self) -> None:
        """Hydrate in-memory domain state from SQLite on startup.

        Restores cooldown timers and failure counts so that a freshly
        restarted scraper doesn't immediately re-bombard a domain that
        was in cooldown.
        """
        try:
            with _POLICY_DB_LOCK:
                conn = _policy_db_conn()
                try:
                    rows = conn.execute(
                        """
                        SELECT domain, consecutive_failures, total_fetches,
                               last_fetch_time, cooldown_until,
                               robots_disallowed, crawl_delay, robots_checked
                        FROM domain_state
                        """
                    ).fetchall()
                finally:
                    conn.close()
            for row in rows:
                domain = row[0]
                state = DomainState(
                    domain=domain,
                    consecutive_failures=row[1],
                    total_fetches=row[2],
                    last_fetch_time=row[3],
                    cooldown_until=row[4],
                    robots_disallowed=set(json.loads(row[5])),
                    crawl_delay=row[6],
                    robots_checked=bool(row[7]),
                )
                self._domains[domain] = state
            if rows:
                logger.info("Loaded %d domain states from SQLite", len(rows))
        except sqlite3.Error:
            logger.warning("Failed to load domain states from SQLite, starting fresh", exc_info=True)

    def _persist_domain(self, domain: str, state: DomainState) -> None:
        """Persist a single domain's state to SQLite.

        Called after record_result (failure/cooldown changes) and after
        robots.txt fetch (disallowed paths). Uses UPSERT to keep the
        row count at one per domain.
        """
        try:
            robots_json = json.dumps(sorted(state.robots_disallowed))
            with _POLICY_DB_LOCK:
                conn = _policy_db_conn()
                try:
                    conn.execute(
                        """
                        INSERT INTO domain_state
                            (domain, consecutive_failures, total_fetches,
                             last_fetch_time, cooldown_until,
                             robots_disallowed, crawl_delay, robots_checked)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(domain) DO UPDATE SET
                            consecutive_failures = excluded.consecutive_failures,
                            total_fetches       = excluded.total_fetches,
                            last_fetch_time     = excluded.last_fetch_time,
                            cooldown_until      = excluded.cooldown_until,
                            robots_disallowed   = excluded.robots_disallowed,
                            crawl_delay         = excluded.crawl_delay,
                            robots_checked      = excluded.robots_checked
                        """,
                        (
                            domain,
                            state.consecutive_failures,
                            state.total_fetches,
                            state.last_fetch_time,
                            state.cooldown_until,
                            robots_json,
                            state.crawl_delay,
                            int(state.robots_checked),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error:
            logger.warning("Failed to persist domain state for %s", domain, exc_info=True)

    @staticmethod
    def _extract_domain(url: str) -> str | None:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or None
        except (ValueError, UnicodeDecodeError):
            return None

    @staticmethod
    def _extract_path(url: str) -> str:
        try:
            return urlparse(url).path or "/"
        except (ValueError, UnicodeDecodeError):
            return "/"

    async def _check_robots_txt(self, domain: str) -> None:
        """Fetch and parse robots.txt for a domain (best-effort)."""
        state = self._get_state(domain)
        state.robots_checked = True

        try:
            from app.url_safety import get_safe_async_client

            url = f"https://{domain}/robots.txt"
            async with get_safe_async_client(
                timeout=settings.ROBOTS_TIMEOUT,
                headers={"User-Agent": settings.USER_AGENT},
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return

                text = resp.text
                current_agent = None
                disallowed_paths: set[str] = set()
                allowed_paths: set[str] = set()
                crawl_delay = 0.0

                for line in text.splitlines():
                    line = line.strip()  # noqa: PLW2901, RUF100
                    if not line or line.startswith("#"):
                        continue

                    if line.lower().startswith("user-agent:"):
                        agent = line.split(":", 1)[1].strip().lower()
                        current_agent = agent if agent == "*" else None
                        continue

                    if current_agent != "*":
                        continue

                    if line.lower().startswith("disallow:"):
                        path = line.split(":", 1)[1].strip()
                        if path:
                            disallowed_paths.add(path)

                    if line.lower().startswith("allow:"):
                        path = line.split(":", 1)[1].strip()
                        if path:
                            allowed_paths.add(path)

                    if line.lower().startswith("crawl-delay:"):
                        with contextlib.suppress(ValueError):
                            crawl_delay = float(line.split(":", 1)[1].strip())

                state.robots_disallowed = disallowed_paths
                state.crawl_delay = crawl_delay
                self._robots_allowed[domain] = allowed_paths

                if disallowed_paths:
                    logger.debug(
                        "robots.txt for %s: %d disallowed paths, %d allowed paths, delay=%.1fs",
                        domain,
                        len(disallowed_paths),
                        len(allowed_paths),
                        crawl_delay,
                    )

                # Persist robots.txt results so we don't re-fetch on restart
                self._persist_domain(domain, state)

        except Exception as e:
            logger.debug("Failed to fetch robots.txt for %s: %s", domain, e)
            # Non-fatal — proceed without robots.txt constraints

    @staticmethod
    def _is_path_disallowed(
        path: str,
        disallowed: set[str],
        allowed: set[str] | None = None,
    ) -> bool:
        """Check if a path is disallowed by robots.txt rules.

        If ``allowed`` is provided, an Allow directive that matches
        takes precedence over a matching Disallow (per RFC 9309 /
        Google spec — the most specific match wins; we use a
        longest-pattern-match heuristic).
        """
        if not disallowed:
            return False

        best_disallow_len = -1
        disallowed_match = False
        for pattern in disallowed:
            if pattern == "/":
                best_disallow_len = max(best_disallow_len, 1)
                disallowed_match = True
                continue
            if pattern.endswith("*"):
                if path.startswith(pattern[:-1]):
                    best_disallow_len = max(best_disallow_len, len(pattern))
                    disallowed_match = True
            elif path == pattern or path.startswith(pattern):
                best_disallow_len = max(best_disallow_len, len(pattern))
                disallowed_match = True

        if not disallowed_match:
            return False

        # Check Allow override — longest match wins
        best_allow_len = -1
        for pattern in allowed or set():
            if pattern.endswith("*"):
                if path.startswith(pattern[:-1]):
                    best_allow_len = max(best_allow_len, len(pattern))
            elif path == pattern or path.startswith(pattern):
                best_allow_len = max(best_allow_len, len(pattern))

        # Allow takes precedence when the allow pattern is at least
        # as long as the disallow pattern (per RFC 9309 §2.2.2).
        return best_allow_len < best_disallow_len


# ─── Singleton Accessor ─────────────────────────────────────────────────

_policy_engine: CrawlPolicyEngine | None = None
_policy_engine_lock = threading.Lock()


def get_crawl_policy() -> CrawlPolicyEngine:
    global _policy_engine
    if _policy_engine is None:
        with _policy_engine_lock:
            if _policy_engine is None:
                _policy_engine = CrawlPolicyEngine()
    return _policy_engine
