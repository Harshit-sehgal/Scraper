"""Geocoding Cache — shared persistent geocoding index to safeguard Nominatim rate-limits.

Provides:
  - SQLite persistence for geocoded location coordinate mappings.
  - Negative caching table to prevent repeating failed queries for 7 days.
  - Cache-hit and avoided request telemetry logs.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
CACHE_DB_PATH = str(_BACKEND_ROOT / "data" / "geocoding_cache.db")
NEGATIVE_CACHE_TTL_DAYS = 7


class GeocodeCache:
    """Manages coordinate lookup persistence, caching lookups to eliminate network overhead."""

    def __init__(self, db_path: str = CACHE_DB_PATH) -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.hits = 0
        self.misses = 0

    def _init_db(self) -> None:
        """Initialize geocode cache SQLite tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS geocoding_cache (
                    query_hash TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    resolved_address TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS negative_cache (
                    query_hash TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.commit()

    def _hash_query(self, query: str) -> str:
        """Create a stable normalized query hash key."""
        normalized = query.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, query: str) -> tuple[float, float, str | None] | None:
        """Fetch coordinates and resolved address from the geocode cache or negative cache."""
        q_hash = self._hash_query(query)

        # 1. Check negative cache first (7-day TTL check)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp FROM negative_cache WHERE query_hash = ?", (q_hash,))
            row = cursor.fetchone()

        if row:
            timestamp = row[0]
            elapsed_days = (time.time() - timestamp) / 86400.0
            if elapsed_days < NEGATIVE_CACHE_TTL_DAYS:
                self.hits += 1
                logger.info("[Geocode Cache] Negative cache HIT for query '%s' (suppressed)", query)
                return (0.0, 0.0, "EXCLUDED_NEGATIVE_CACHE")
            # Expired negative cache entry
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM negative_cache WHERE query_hash = ?", (q_hash,))
                conn.commit()

        # 2. Check primary geocoding cache
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lat, lon, resolved_address FROM geocoding_cache WHERE query_hash = ?", (q_hash,))
            row = cursor.fetchone()

        if row:
            self.hits += 1
            logger.info("[Geocode Cache] Cache HIT for query '%s' -> (%.4f, %.4f)", query, row[0], row[1])
            return (row[0], row[1], row[2])

        self.misses += 1
        return None

    def set(self, query: str, lat: float, lon: float, resolved_address: str | None = None) -> None:
        """Store coordinates in the geocoding cache."""
        q_hash = self._hash_query(query)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO geocoding_cache VALUES (?, ?, ?, ?, ?, ?)",
                (q_hash, query, lat, lon, resolved_address, time.time()),
            )
            conn.commit()
        logger.info("[Geocode Cache] Cached coordinates for query '%s' -> (%.4f, %.4f)", query, lat, lon)

    def set_negative(self, query: str) -> None:
        """Mark a query as failed in the negative cache to suppress retries."""
        q_hash = self._hash_query(query)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO negative_cache VALUES (?, ?, ?)", (q_hash, query, time.time()))
            conn.commit()
        logger.info("[Geocode Cache] Cached negative failure for query '%s'", query)

    def get_hit_rate(self) -> float:
        """Compute the cache hit rate metric."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


# Global geocode cache singleton instances
_geocode_cache: GeocodeCache | None = None


def get_geocode_cache() -> GeocodeCache:
    """Lazy bootstrap cache instance to support multi-node worker contexts."""
    global _geocode_cache
    if _geocode_cache is None:
        _geocode_cache = GeocodeCache()
    return _geocode_cache


def reset_geocode_cache() -> None:
    """Reset the global singleton (used in tests to avoid cross-test pollution)."""
    global _geocode_cache
    _geocode_cache = None
