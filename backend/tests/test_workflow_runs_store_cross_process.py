"""Cross-process regression tests for the file-backed WorkflowRunStore.

Pins the same multi-worker visibility contract that the auth-profile
and scheduled-jobs stores use: writes from any worker must be
immediately visible to any other worker opening the same path.
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

from app.utils.workflow_run_store import WorkflowRunStore


@pytest.fixture
def store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "workflow_runs.json"
    monkeypatch.setenv("DATAFORGE_WORKFLOW_RUNS_FILE", str(path))
    yield path
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    with contextlib.suppress(FileNotFoundError):
        Path(str(path) + ".lock").unlink()


def test_two_store_instances_share_visible_writes(store_path: Path) -> None:
    """Worker A upserts; worker B (separate instance) sees the record."""
    a = WorkflowRunStore(path=store_path)
    b = WorkflowRunStore(path=store_path)
    assert b.values() == []
    a.upsert("run-1", {"run_id": "run-1", "workflow_id": "wf-1", "status": "queued"})
    readback = b.get("run-1")
    assert readback is not None
    assert readback["status"] == "queued"
    assert b.values() == [readback]


def test_status_update_visible_to_other_worker(store_path: Path) -> None:
    """A worker that flips queued → succeeded is seen by the other worker."""
    a = WorkflowRunStore(path=store_path)
    b = WorkflowRunStore(path=store_path)
    a.upsert("r", {"run_id": "r", "workflow_id": "wf-1", "status": "queued"})
    b.merge("r", {"status": "succeeded", "finished_at": "2026-06-16T00:00:00+00:00"})
    seen = a.get("r")
    assert seen is not None
    assert seen["status"] == "succeeded"
    assert seen["finished_at"] == "2026-06-16T00:00:00+00:00"


def test_concurrent_writers_dont_clobber(store_path: Path) -> None:
    """N threads writing distinct run ids must all be recoverable."""
    n_threads = 16
    errors: list[str] = []

    def writer(run_id: str, wf_id: str) -> None:
        try:
            WorkflowRunStore(path=store_path).upsert(
                run_id,
                {"run_id": run_id, "workflow_id": wf_id, "status": "queued"},
            )
        except Exception as exc:
            errors.append(f"{run_id}: {exc!r}")

    threads = [threading.Thread(target=writer, args=(f"run-{i}", f"wf-{i}")) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    for t in threads:
        assert not t.is_alive()

    assert not errors, errors
    reader = WorkflowRunStore(path=store_path)
    seen = {r["run_id"] for r in reader.values()}
    assert len(seen) == n_threads


def test_corrupt_store_recovers(store_path: Path) -> None:
    """A corrupt JSON file must not crash reads; the next upsert must succeed."""
    store_path.write_text("not-json{", encoding="utf-8")
    s = WorkflowRunStore(path=store_path)
    assert s.values() == []
    s.upsert("after-corrupt", {"run_id": "after-corrupt", "status": "queued"})
    recovered = s.get("after-corrupt")
    assert recovered is not None
    assert recovered["status"] == "queued"
