"""Cross-process regression tests for the scheduled-monitoring store refactor.

These tests pin multi-worker visibility for the JSONFileStore-backed
``_scheduled_jobs`` in ``backend/app/routers/scheduled_monitoring.py``:
writes from any process must be immediately visible to any other
process opening the same path, and writes must not be lost on
concurrent access. Mirrors ``test_auth_profile_store_cross_process.py``.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

# Pin the same env the production router expects.
os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_API_KEY", "u")
os.environ.setdefault("DATAFORGE_OPERATOR_API_KEY", "o")
os.environ.setdefault("DATAFORGE_ADMIN_API_KEY", "a")
os.environ.setdefault("DATAFORGE_SESSION_SECRET", "test")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")

from app.utils.json_file_store import JSONFileStore


@pytest.fixture
def store_path(tmp_path: Path) -> Iterator[Path]:
    """Per-test JSON file for the scheduled-monitoring store."""
    path = tmp_path / "scheduled_jobs.json"
    yield path
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    with contextlib.suppress(FileNotFoundError):
        Path(str(path) + ".lock").unlink()


def test_two_store_instances_share_visible_writes(store_path: Path) -> None:
    """Worker A's upsert is visible to worker B (separate instance)."""
    worker_a = JSONFileStore(path=store_path)
    worker_b = JSONFileStore(path=store_path)
    assert worker_b.values() == []

    worker_a.upsert("schedule-1", {"id": "schedule-1", "name": "cross-process-recurring"})
    readback = worker_b.get("schedule-1")
    assert readback is not None
    assert readback["name"] == "cross-process-recurring"


def test_delete_visible_across_workers(store_path: Path) -> None:
    """A delete from worker B disappears from worker A immediately."""
    a = JSONFileStore(path=store_path)
    b = JSONFileStore(path=store_path)
    a.upsert("schedule-x", {"id": "schedule-x", "name": "delete-me"})
    assert b.get("schedule-x") is not None

    removed = b.delete("schedule-x")
    assert removed is True
    assert a.get("schedule-x") is None
    assert a.values() == []


def test_merge_visible_across_workers(store_path: Path) -> None:
    """merge from one worker is visible to the other."""
    a = JSONFileStore(path=store_path)
    b = JSONFileStore(path=store_path)
    a.upsert("s", {"id": "s", "name": "baseline", "enabled": True})
    merged = b.merge("s", {"enabled": False})

    assert merged is not None
    assert merged["enabled"] is False
    assert merged["name"] == "baseline"
    merged_a = a.get("s")
    assert merged_a is not None
    assert merged_a["enabled"] is False

    assert b.merge("never-existed", {"x": 1}) is None


def test_concurrent_writers_dont_clobber_each_other(store_path: Path) -> None:
    """N threads with N independent store instances write distinct records;
    every record is recoverable after the dust settles (flock-serialised)."""
    n_threads = 16
    errors: list[str] = []

    def writer(record_id: str, name: str) -> None:
        try:
            store = JSONFileStore(path=store_path)
            store.upsert(record_id, {"id": record_id, "name": name})
        except Exception as exc:
            errors.append(f"{record_id}: {exc!r}")

    threads = [threading.Thread(target=writer, args=(f"recurring-{i}", f"writer-{i}")) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    for t in threads:
        assert not t.is_alive(), "thread hung past 15s"

    assert not errors, errors
    reader = JSONFileStore(path=store_path)
    seen = {r["id"]: r["name"] for r in reader.values()}
    assert len(seen) == n_threads
    for i in range(n_threads):
        assert seen[f"recurring-{i}"] == f"writer-{i}"


def test_corrupt_store_recovers_to_empty(store_path: Path) -> None:
    """A corrupt JSON file must not crash reads; subsequent upsert succeeds."""
    store_path.write_text("this-is-not-json{", encoding="utf-8")
    s = JSONFileStore(path=store_path)
    assert s.values() == []
    s.upsert("after-corrupt", {"id": "after-corrupt", "name": "ok"})
    assert s.get("after-corrupt")["name"] == "ok"


def test_clear_all_is_total(store_path: Path) -> None:
    s = JSONFileStore(path=store_path)
    for i in range(5):
        s.upsert(f"schedule-{i}", {"id": f"schedule-{i}", "name": f"n{i}"})
    assert len(s) == 5
    removed = s.clear_all()
    assert removed == 5
    assert len(s) == 0
    assert s.values() == []
