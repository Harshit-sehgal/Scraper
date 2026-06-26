"""F-ANTIBOT-COOKIE-001: Cookie persistence for anti-bot engine.

Verifies that ``AntiBotEngine.update_cookies`` persists cookies to SQLite
so they survive process restarts, and that cookies are hydrated from the
database on engine initialisation.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from app.anti_bot_engine import AntiBotEngine, _cookie_db_conn


class TestCookiePersistence:
    """SQLite-backed cookie store for cf_clearance etc."""

    def test_update_cookies_writes_to_sqlite(self, tmp_path: Path) -> None:
        """update_cookies must persist to SQLite, not just the in-memory dict."""
        db_path = tmp_path / "cookies.db"
        engine = AntiBotEngine()
        # Patch the DB path so writes go to our temp location
        with patch("app.anti_bot_engine._cookie_db_path", return_value=db_path):
            engine.update_cookies("example.com", "cf_clearance=abc123; session=xyz")

            # Verify in-memory cache
            assert engine.get_cookies("example.com") == "cf_clearance=abc123; session=xyz"

            # Verify SQLite directly
            conn = _cookie_db_conn(db_path)
            row = conn.execute(
                "SELECT cookie_string, updated_at FROM cookies WHERE domain = ?",
                ("example.com",),
            ).fetchone()
            conn.close()
            assert row is not None
            assert row[0] == "cf_clearance=abc123; session=xyz"
            assert row[1] > 0

    def test_cookies_survive_restart(self, tmp_path: Path) -> None:
        """A new engine instance must load previously persisted cookies."""
        db_path = tmp_path / "cookies.db"

        # Engine 1 writes cookies
        with patch("app.anti_bot_engine._cookie_db_path", return_value=db_path):
            engine1 = AntiBotEngine()
            engine1.update_cookies("shop.example.com", "cf_clearance=token789")

        # Engine 2 (fresh process) must see them on startup
        # Need to clear the initialised set so the new engine re-creates
        from app.anti_bot_engine import _COOKIE_DB_INITIALIZED

        _COOKIE_DB_INITIALIZED.discard(db_path)

        with patch("app.anti_bot_engine._cookie_db_path", return_value=db_path):
            engine2 = AntiBotEngine()
            assert engine2.get_cookies("shop.example.com") == "cf_clearance=token789"

    def test_cookies_overwrite_on_update(self, tmp_path: Path) -> None:
        """Subsequent update_cookies calls must overwrite, not duplicate."""
        db_path = tmp_path / "cookies.db"

        with patch("app.anti_bot_engine._cookie_db_path", return_value=db_path):
            engine = AntiBotEngine()
            engine.update_cookies("cdn.test.com", "old=value")
            engine.update_cookies("cdn.test.com", "new=value")

            assert engine.get_cookies("cdn.test.com") == "new=value"

            conn = _cookie_db_conn(db_path)
            rows = conn.execute(
                "SELECT cookie_string FROM cookies WHERE domain = ?",
                ("cdn.test.com",),
            ).fetchall()
            conn.close()
            assert len(rows) == 1, "must have exactly 1 row per domain (upsert)"
            assert rows[0][0] == "new=value"

    def test_update_cookies_noop_on_empty(self, tmp_path: Path) -> None:
        """Empty domain or cookie_string must not write to the DB."""
        db_path = tmp_path / "cookies.db"
        with patch("app.anti_bot_engine._cookie_db_path", return_value=db_path):
            engine = AntiBotEngine()
            engine.update_cookies("", "cf_clearance=abc")
            engine.update_cookies("example.com", "")
            engine.update_cookies("", "")

            conn = _cookie_db_conn(db_path)
            count = conn.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
            conn.close()
            assert count == 0, "empty inputs must not create rows"

    def test_should_refresh_cookies(self, tmp_path: Path) -> None:
        """should_refresh_cookies must return True when cookies are stale."""
        engine = AntiBotEngine()
        # No cookies stored → should refresh
        assert engine.should_refresh_cookies("unknown.com")

        # Just set → should not refresh (max_age default = 24h)
        engine.update_cookies("fresh.com", "cf_clearance=abc")
        assert not engine.should_refresh_cookies("fresh.com")

        # Simulate an old update time
        engine._last_cookie_update["stale.com"] = time.time() - 25 * 3600  # 25h ago
        assert engine.should_refresh_cookies("stale.com", max_age_hours=24)

    def test_db_corruption_handled_gracefully(self, tmp_path: Path) -> None:
        """If the cookie DB is corrupt, the engine must not crash on init."""
        db_path = tmp_path / "cookies.db"
        # Write garbage
        db_path.write_bytes(b"\x00\x01\x02bad-data")

        from app.anti_bot_engine import _COOKIE_DB_INITIALIZED

        _COOKIE_DB_INITIALIZED.discard(db_path)

        # Constructor must not raise
        with patch("app.anti_bot_engine._cookie_db_path", return_value=db_path):
            engine = AntiBotEngine()
        # Cookies will just be empty
        assert engine.get_cookies("any.com") == ""
