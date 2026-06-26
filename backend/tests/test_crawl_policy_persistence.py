"""F-CRAWL-POLICY-001: Persist crawl policy domain state across restarts.

Verifies that ``CrawlPolicyEngine`` persists cooldown timers and failure
counts to SQLite so domain cooldowns survive process/container restarts.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.crawl_policy import (
    CrawlPolicyEngine,
    _policy_db_conn,
)


class TestDomainStatePersistence:
    """SQLite-backed cooldown and failure state."""

    def test_record_failure_persists_to_sqlite(self, tmp_path: Path) -> None:
        """Failures must be persisted so they survive restarts."""
        db_path = tmp_path / "crawl_policy.db"

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine = CrawlPolicyEngine()

            # Record 5 consecutive failures → triggers cooldown
            for _ in range(5):
                engine.record_result("https://evil.com/page", success=False)

            state = engine.get_domain_state("evil.com")
            assert state is not None
            assert state["consecutive_failures"] >= 5

            # Verify SQLite directly
            conn = _policy_db_conn(db_path)
            row = conn.execute(
                "SELECT consecutive_failures, cooldown_until FROM domain_state WHERE domain = ?",
                ("evil.com",),
            ).fetchone()
            conn.close()
            assert row is not None
            assert row[0] == state["consecutive_failures"]
            assert row[1] > 0  # cooldown_until is in the future

    def test_cooldown_survives_restart(self, tmp_path: Path) -> None:
        """A domain placed in cooldown must still be in cooldown after restart."""
        db_path = tmp_path / "crawl_policy.db"

        # Engine 1 puts domain into cooldown
        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine1 = CrawlPolicyEngine()
            for _ in range(5):
                engine1.record_result("https://blocked.example.org/page", success=False)

        # Engine 2 (simulates restart) must see cooldown
        from app.crawl_policy import _POLICY_DB_INITIALIZED

        _POLICY_DB_INITIALIZED.discard(db_path)

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine2 = CrawlPolicyEngine()
            state = engine2.get_domain_state("blocked.example.org")
            assert state is not None
            assert state["cooldown"] > 0, (
                "Domain in cooldown must still be cooling down after restart"
            )

    def test_success_clears_failures_in_db(self, tmp_path: Path) -> None:
        """A successful fetch resets failure count to 0, persisted."""
        db_path = tmp_path / "crawl_policy.db"

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine = CrawlPolicyEngine()
            engine.record_result("https://site.com", success=False)
            engine.record_result("https://site.com", success=False)
            engine.record_result("https://site.com", success=True)

            state = engine.get_domain_state("site.com")
            assert state["consecutive_failures"] == 0

            conn = _policy_db_conn(db_path)
            row = conn.execute(
                "SELECT consecutive_failures FROM domain_state WHERE domain = ?",
                ("site.com",),
            ).fetchone()
            conn.close()
            assert row is not None
            assert row[0] == 0

    def test_robots_disallowed_persisted(self, tmp_path: Path) -> None:
        """Robots.txt cache must persist so we don't re-fetch on restart."""
        db_path = tmp_path / "crawl_policy.db"

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine = CrawlPolicyEngine()
            # Directly set state as _check_robots_txt does
            from app.crawl_policy import DomainState

            state = DomainState(domain="shop.test")
            state.robots_disallowed = {"/admin", "/api/"}
            state.crawl_delay = 5.0
            state.robots_checked = True
            engine._domains["shop.test"] = state
            engine._persist_domain("shop.test", state)

        # Fresh engine loads it back
        from app.crawl_policy import _POLICY_DB_INITIALIZED

        _POLICY_DB_INITIALIZED.discard(db_path)

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine2 = CrawlPolicyEngine()
            ds = engine2.get_domain_state("shop.test")
            assert ds is not None
            assert ds["robots_checked"] is True

            # Access internal state to verify robots_disallowed
            raw = engine2._domains.get("shop.test")
            assert raw is not None
            assert "/admin" in raw.robots_disallowed
            assert raw.crawl_delay == 5.0

    def test_reset_domain_removes_from_db(self, tmp_path: Path) -> None:
        """reset_domain must clear both in-memory and SQLite state."""
        db_path = tmp_path / "crawl_policy.db"

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine = CrawlPolicyEngine()
            engine.record_result("https://temp.example.com", success=False)
            engine.record_result("https://temp.example.com", success=False)

            assert "temp.example.com" in engine._domains

            engine.reset_domain("https://temp.example.com")
            assert "temp.example.com" not in engine._domains

            # Verify DB row is gone
            conn = _policy_db_conn(db_path)
            row = conn.execute(
                "SELECT 1 FROM domain_state WHERE domain = ?",
                ("temp.example.com",),
            ).fetchone()
            conn.close()
            assert row is None

    def test_load_empty_db_is_harmless(self, tmp_path: Path) -> None:
        """A fresh engine with no DB records must not crash."""
        db_path = tmp_path / "crawl_policy.db"
        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine = CrawlPolicyEngine()
            assert engine._domains == {}

    def test_db_corruption_handled_gracefully(self, tmp_path: Path) -> None:
        """Corrupt DB must not crash the engine on init."""
        db_path = tmp_path / "crawl_policy.db"
        db_path.write_bytes(b"\x00\x01\x02garbage")

        from app.crawl_policy import _POLICY_DB_INITIALIZED

        _POLICY_DB_INITIALIZED.discard(db_path)

        with patch("app.crawl_policy._policy_db_path", return_value=db_path):
            engine = CrawlPolicyEngine()
        # Engine must still be functional
        assert engine.get_domain_state("any.domain") is None
