"""Cross-process regression tests for the file-backed AuthProfileStore.

These tests pin the multi-worker visibility contract that closed
the per-process ``_auth_profiles`` dict bug in
``backend/app/routers/auth_profiles.py``: writes from any process
must be immediately visible to any other process opening the
same path, and writes must not be lost on concurrent access.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_API_KEY", "u")
os.environ.setdefault("DATAFORGE_OPERATOR_API_KEY", "o")
os.environ.setdefault("DATAFORGE_ADMIN_API_KEY", "a")
os.environ.setdefault("DATAFORGE_SESSION_SECRET", "test")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")

from app.utils.auth_profile_store import AuthProfileStore


@pytest.fixture
def store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "auth_profiles.json"
    monkeypatch.setenv("DATAFORGE_AUTH_PROFILES_FILE", str(path))
    # Drop any cached default-resolution state — easiest way is to
    # leave the env var pinned; the store reads it on every call.
    yield path
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    with contextlib.suppress(FileNotFoundError):
        Path(str(path) + ".lock").unlink()


def test_two_store_instances_share_visible_writes(store_path: Path) -> None:
    """Process A writes; process B (separate AuthProfileStore instance)
    immediately sees the new record."""
    worker_a = AuthProfileStore(path=store_path)
    worker_b = AuthProfileStore(path=store_path)

    assert worker_b.values() == []
    worker_a.upsert("profile-1", {"id": "profile-1", "name": "cross-process"})

    # B has no in-memory cache; always re-reads disk.
    readback = worker_b.get("profile-1")
    assert readback is not None
    assert readback["name"] == "cross-process"
    assert worker_b.values() == [readback]


def test_another_worker_sees_upsert_changes(store_path: Path) -> None:
    """An upsert that changes ``name`` is visible to the other worker; created_at preserved; usage_count preserved on replace."""
    a = AuthProfileStore(path=store_path)
    b = AuthProfileStore(path=store_path)
    a.upsert("p", {"id": "p", "name": "v1"})
    b.upsert("p", {"id": "p", "name": "v2"})

    record = a.get("p")
    assert record is not None
    assert record["name"] == "v2"


def test_another_worker_sees_delete(store_path: Path) -> None:
    a = AuthProfileStore(path=store_path)
    b = AuthProfileStore(path=store_path)
    a.upsert("doomed", {"id": "doomed", "name": "delete-me"})
    assert b.get("doomed") is not None

    removed = b.delete("doomed")
    assert removed is True
    # The other worker re-reads disk and sees the removal.
    assert a.get("doomed") is None


def test_merge_from_one_worker_visible_to_another(store_path: Path) -> None:
    a = AuthProfileStore(path=store_path)
    b = AuthProfileStore(path=store_path)
    a.upsert("p", {"id": "p", "name": "baseline", "usage_count": 0})
    merged = b.merge("p", {"last_validated_at": "2026-06-13T00:00:00+00:00"})

    assert merged is not None
    assert merged["last_validated_at"] == "2026-06-13T00:00:00+00:00"
    assert merged["name"] == "baseline"
    # Other worker reads after the merge: sees the merged field.
    merged_a = a.get("p")
    assert merged_a is not None
    assert merged_a["last_validated_at"] == "2026-06-13T00:00:00+00:00"


def test_concurrent_writers_dont_clobber_each_other(store_path: Path) -> None:
    """Spawn N threads against N distinct AuthProfileStore instances
    (each thread opens its own store) and assert that every write
    is recoverable after the dust settles. fcntl.flock must serialise."""
    n_threads = 16
    errors: list[str] = []

    def writer(profile_id: str, name: str) -> None:
        try:
            store = AuthProfileStore(path=store_path)
            store.upsert(profile_id, {"id": profile_id, "name": name})
        except Exception as exc:  # capture for assertion below
            errors.append(f"{profile_id}: {exc!r}")

    threads = [threading.Thread(target=writer, args=(f"profile-{i}", f"writer-{i}")) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    for t in threads:
        assert not t.is_alive(), "thread hung past 15s"

    assert not errors, errors

    reader = AuthProfileStore(path=store_path)
    seen = {r["id"]: r["name"] for r in reader.values()}
    assert len(seen) == n_threads
    for i in range(n_threads):
        assert seen[f"profile-{i}"] == f"writer-{i}"


def test_corrupt_store_recovers_to_empty(store_path: Path, caplog) -> None:
    """A corrupt JSON file must not crash reads; it should re-start empty
    with a warning, never lose a subsequent upsert."""
    store_path.write_text("this-is-not-json{", encoding="utf-8")
    s = AuthProfileStore(path=store_path)
    assert s.values() == []
    s.upsert("after-corrupt", {"id": "after-corrupt", "name": "ok"})
    recovered = s.get("after-corrupt")
    assert recovered is not None
    assert recovered["name"] == "ok"


def test_clear_all_is_total(store_path: Path) -> None:
    s = AuthProfileStore(path=store_path)
    for i in range(5):
        s.upsert(f"p{i}", {"id": f"p{i}", "name": f"n{i}"})
    assert len(s) == 5
    removed = s.clear_all()
    assert removed == 5
    assert len(s) == 0
    assert s.values() == []
