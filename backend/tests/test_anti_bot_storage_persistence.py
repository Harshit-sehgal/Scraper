from __future__ import annotations

import tempfile
from pathlib import Path

from app.anti_bot_engine import (
    AntiBotEngine,
    _cookie_db_conn,
    _cookie_db_path,
)


class TestStoragePersistence:
    def _engine(self) -> AntiBotEngine:
        return AntiBotEngine()

    def test_cookie_db_path_resolves(self) -> None:
        path = _cookie_db_path()
        assert isinstance(path, Path)
        assert path.name == "anti_bot_cookies.db"

    def test_cookie_db_conn_creates_table(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            conn = _cookie_db_conn(db_path=tmp_path)
            try:
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cookies'").fetchall()
                assert len(tables) == 1
            finally:
                conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_update_and_get_cookies_roundtrip(self) -> None:
        engine = self._engine()
        engine.update_cookies("store.test", "key=stored_value")
        assert engine.get_cookies("store.test") == "key=stored_value"

    def test_update_cookies_overwrites(self) -> None:
        engine = self._engine()
        engine.update_cookies("overwrite.test", "first=value")
        engine.update_cookies("overwrite.test", "second=replaced")
        assert engine.get_cookies("overwrite.test") == "second=replaced"

    def test_record_block_then_success(self) -> None:
        engine = self._engine()
        engine.record_block("flaky.com", 0.95)
        engine.record_success("flaky.com")
        assert engine.get_cookies("flaky.com") == ""
