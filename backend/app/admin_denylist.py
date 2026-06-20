"""Persistent admin domain denylist (P1-COMPLIANCE-001).

Stores a list of target domains the administrator has marked as
"do not scrape" — for example, sites that have sent takedown notices,
sites the operator has chosen to exclude for legal/ethical reasons, or
sites that are known to be unreliable. The URL-safety check
(``app.url_safety.validate_public_http_url``) consults this list on
every scrape and rejects matching URLs.

Storage
-------
SQLite, keyed on lowercase hostname. The same SQLite file as the
job store is used by default (``DATAFORGE_JOB_STORE_PATH``); a
dedicated file is also supported via ``DATAFORGE_DENYLIST_DB_PATH``.

The module deliberately keeps the schema tiny — denylist entries
are write-rare, read-often, and the schema is forward-compatible
with later P1-COMPLIANCE-001 work (per-domain reason codes, admin
approval, etc.).

Schema::

    CREATE TABLE IF NOT EXISTS domain_denylist (
        domain TEXT PRIMARY KEY,
        reason TEXT NOT NULL DEFAULT '',
        added_by TEXT NOT NULL DEFAULT '',
        added_at TEXT NOT NULL DEFAULT (datetime('now')),
        path_prefix TEXT NOT NULL DEFAULT ''  -- '' means whole domain
    );

Concurrency
-----------
The module is safe to use from multiple threads via an internal
``threading.RLock``. Reads (the hot path on every scrape) are
lock-free after a small in-memory cache; writes clear the cache.

Public API
----------
- :class:`DomainDenylist` -- the store
- :func:`get_denylist` -- module-level singleton accessor (test override via
  :func:`set_denylist`)
- :func:`is_blocked` -- convenience: is *url* blocked by the singleton?
- :func:`validate_against_denylist` -- raises ``ValueError`` if blocked
  (matches the contract of ``validate_public_http_url``)
"""

from __future__ import annotations

import builtins
import logging
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DENYLIST_TABLE = "domain_denylist"

DEFAULT_DB_PATH = "dataforge_denylist.sqlite"
# In-process cache TTL — denylist reads are on the hot path of every
# scrape, but writes are rare (admin-only). A 5-second TTL keeps the
# in-memory view fresh enough that an admin takedown takes effect
# within seconds, without re-reading the DB on every request.
_CACHE_TTL_SECONDS = 5.0


@dataclass(frozen=True)
class DenylistEntry:
    """A single denylist row."""

    domain: str
    reason: str
    added_by: str
    added_at: str
    path_prefix: str = ""

    def blocks(self, url: str) -> bool:
        """Return True if *url* is blocked by this entry.

        A ``path_prefix`` of ``""`` blocks the whole domain. A non-empty
        prefix blocks only URLs whose path starts with the prefix.
        """
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host != self.domain:
            return False
        if not self.path_prefix:
            return True
        return (parsed.path or "/").startswith(self.path_prefix)


class DomainDenylist:
    """Persistent admin domain denylist.

    The store is keyed on lowercase hostname. Path prefixes allow
    blocking only a sub-tree of a domain (e.g. ``/private``).
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._cache: dict[str, list[DenylistEntry]] = {}
        self._cache_loaded_at: float = 0.0
        self._ensure_schema()

    # ── Schema ──────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {DENYLIST_TABLE} (
                    domain TEXT PRIMARY KEY,
                    reason TEXT NOT NULL DEFAULT '',
                    added_by TEXT NOT NULL DEFAULT '',
                    added_at TEXT NOT NULL DEFAULT (datetime('now')),
                    path_prefix TEXT NOT NULL DEFAULT ''
                )
                """,
            )

    # ── Cache ────────────────────────────────────────────────────────

    def _cache_valid(self) -> bool:
        return bool(self._cache) and (time.monotonic() - self._cache_loaded_at) < _CACHE_TTL_SECONDS

    def _load_cache(self) -> None:
        with self._lock, self._connect() as conn:
            query = f"SELECT domain, reason, added_by, added_at, path_prefix FROM {DENYLIST_TABLE}"  # nosec B608, noqa: S608
            rows = conn.execute(query).fetchall()
        self._cache = {}
        for row in rows:
            entry = DenylistEntry(
                domain=str(row["domain"]).lower(),
                reason=str(row["reason"] or ""),
                added_by=str(row["added_by"] or ""),
                added_at=str(row["added_at"] or ""),
                path_prefix=str(row["path_prefix"] or ""),
            )
            self._cache.setdefault(entry.domain, []).append(entry)
        self._cache_loaded_at = time.monotonic()

    def _invalidate_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_loaded_at = 0.0

    # ── CRUD ────────────────────────────────────────────────────────

    def add(
        self,
        domain: str,
        *,
        reason: str = "",
        added_by: str = "",
        path_prefix: str = "",
    ) -> DenylistEntry:
        """Add a denylist entry. Idempotent (overwrites reason on duplicate)."""
        domain = (domain or "").strip().lower()
        if not domain:
            msg = "domain is required"
            raise ValueError(msg)
        if not all(c.isalnum() or c in ".-" for c in domain):
            msg = f"invalid domain: {domain!r}"
            raise ValueError(msg)
        with self._lock, self._connect() as conn:
            query = f"""
                INSERT INTO {DENYLIST_TABLE} (domain, reason, added_by, path_prefix)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    reason=excluded.reason,
                    added_by=excluded.added_by,
                    added_at=datetime('now'),
                    path_prefix=excluded.path_prefix
                """  # nosec B608, noqa: S608
            conn.execute(query, (domain, reason, added_by, path_prefix))
        self._invalidate_cache()
        return DenylistEntry(
            domain=domain,
            reason=reason,
            added_by=added_by,
            added_at="",
            path_prefix=path_prefix,
        )

    def remove(self, domain: str, *, path_prefix: str = "") -> bool:
        """Remove a denylist entry. Returns True if a row was deleted."""
        domain = (domain or "").strip().lower()
        with self._lock, self._connect() as conn:
            if path_prefix:
                query = f"DELETE FROM {DENYLIST_TABLE} WHERE domain = ? AND path_prefix = ?"  # nosec B608, noqa: S608
                cur = conn.execute(query, (domain, path_prefix))
            else:
                query = f"DELETE FROM {DENYLIST_TABLE} WHERE domain = ?"  # nosec B608, noqa: S608
                cur = conn.execute(query, (domain,))
        self._invalidate_cache()
        return cur.rowcount > 0

    def list(self) -> builtins.list[DenylistEntry]:
        """Return all denylist entries."""
        with self._lock:
            if not self._cache_valid():
                self._load_cache()
            out: list[DenylistEntry] = []
            for entries in self._cache.values():
                out.extend(entries)
            out.sort(key=lambda e: (e.domain, e.path_prefix))
            return out

    def get(self, domain: str) -> builtins.list[DenylistEntry]:
        """Return all entries for *domain* (whole-domain and path-prefix)."""
        domain = (domain or "").strip().lower()
        with self._lock:
            if not self._cache_valid():
                self._load_cache()
            return list(self._cache.get(domain, []))

    def is_blocked(self, url: str) -> DenylistEntry | None:
        """Return the entry that blocks *url*, or None if allowed."""
        try:
            host = (urlparse(url).hostname or "").lower()
        except (TypeError, ValueError):
            return None
        if not host:
            return None
        with self._lock:
            if not self._cache_valid():
                self._load_cache()
            for entry in self._cache.get(host, ()):
                if entry.blocks(url):
                    return entry
        return None

    def validate_url(self, url: str) -> None:
        """Raise ``ValueError`` if *url* is blocked.

        Mirrors the contract of the module-level
        :func:`validate_against_denylist`.
        """
        entry = self.is_blocked(url)
        if entry is None:
            return
        suffix = f" (path: {entry.path_prefix})" if entry.path_prefix else ""
        msg = (
            f"URL hostname '{entry.domain}' is on the admin denylist and may not be scraped.{suffix} "
            f"Reason: {entry.reason or 'not specified'}."
        )
        raise ValueError(msg)

    def clear(self) -> None:
        """Remove every entry (test helper)."""
        with self._lock, self._connect() as conn:
            query = f"DELETE FROM {DENYLIST_TABLE}"  # nosec B608, noqa: S608
            conn.execute(query)
        self._invalidate_cache()

    def close(self) -> None:
        """Drop the in-memory cache; connection is per-call so no fd to close."""
        with self._lock:
            self._cache.clear()
            self._cache_loaded_at = 0.0


# ── Module-level singleton ──────────────────────────────────────────

_singleton: DomainDenylist | None = None
_singleton_lock = threading.Lock()


def get_denylist() -> DomainDenylist:
    """Return the process-wide singleton :class:`DomainDenylist`."""
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is None:
            try:
                from app.config import settings

                db_path = getattr(settings, "DENYLIST_DB_PATH", "") or DEFAULT_DB_PATH
            except ImportError:
                logger.debug("Failed to load DENYLIST_DB_PATH from settings", exc_info=True)
                db_path = DEFAULT_DB_PATH
            except AttributeError:
                logger.debug("settings object has no DENYLIST_DB_PATH, using default", exc_info=True)
                db_path = DEFAULT_DB_PATH
            _singleton = DomainDenylist(db_path=db_path)
    return _singleton


def set_denylist(instance: DomainDenylist | None) -> None:
    """Replace the singleton (test helper). Pass None to reset."""
    global _singleton
    with _singleton_lock:
        _singleton = instance


def is_blocked(url: str) -> DenylistEntry | None:
    """Convenience: is *url* blocked by the singleton?"""
    return get_denylist().is_blocked(url)


def validate_against_denylist(url: str) -> None:
    """Raise ``ValueError`` if *url* is in the denylist.

    Mirrors the contract of :func:`app.url_safety.validate_public_http_url`
    so callers can use the same try/except pattern.
    """
    entry = is_blocked(url)
    if entry is None:
        return
    suffix = f" (path: {entry.path_prefix})" if entry.path_prefix else ""
    msg = (
        f"URL hostname '{entry.domain}' is on the admin denylist and may not be scraped.{suffix} "
        f"Reason: {entry.reason or 'not specified'}."
    )
    raise ValueError(msg)


def collect_denied_domains(entries: Iterable[DenylistEntry]) -> set[str]:
    """Return the set of unique hostnames in *entries* (test helper)."""
    return {e.domain for e in entries}
