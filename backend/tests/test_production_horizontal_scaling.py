from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from app.worker_queue import Priority, WorkerQueue


@pytest.fixture
def _queue_db() -> Generator[Path]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    yield tmp_path
    tmp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_enqueue_dequeue_roundtrip(_queue_db: Path) -> None:
    q = WorkerQueue(max_concurrency=10, db_path=_queue_db)
    tid = await q.enqueue("test_task", {"key": "value"}, priority=Priority.HIGH)
    assert tid is not None
    task = await q.dequeue()
    assert task is not None
    assert task.id == tid
    assert task.type == "test_task"
    assert task.payload == {"key": "value"}


@pytest.mark.asyncio
async def test_priority_ordering(_queue_db: Path) -> None:
    q = WorkerQueue(max_concurrency=10, db_path=_queue_db)
    await q.enqueue("low", {"x": 1}, priority=Priority.LOW)
    await q.enqueue("high", {"x": 2}, priority=Priority.HIGH)
    await q.enqueue("critical", {"x": 3}, priority=Priority.CRITICAL)
    first = await q.dequeue()
    assert first is not None
    assert first.type == "critical"
    second = await q.dequeue()
    assert second is not None
    assert second.type == "high"
    third = await q.dequeue()
    assert third is not None
    assert third.type == "low"


@pytest.mark.asyncio
async def test_concurrent_enqueues_from_multiple_sources(_queue_db: Path) -> None:
    q = WorkerQueue(max_concurrency=10, db_path=_queue_db)

    async def enqueue_task(name: str) -> str:
        return await q.enqueue(name, {"from": name}, priority=Priority.NORMAL)

    tids = await asyncio.gather(enqueue_task("a"), enqueue_task("b"), enqueue_task("c"))
    assert len(set(tids)) == 3
    task_a = await q.dequeue()
    task_b = await q.dequeue()
    task_c = await q.dequeue()
    assert task_a is not None
    assert task_b is not None
    assert task_c is not None
    assert {task_a.id, task_b.id, task_c.id} == set(tids)


@pytest.mark.asyncio
async def test_max_concurrency_respected(_queue_db: Path) -> None:
    q = WorkerQueue(max_concurrency=2, db_path=_queue_db)
    assert q._max_concurrency == 2
    q.set_max_concurrency(5)
    assert q._max_concurrency == 5


@pytest.mark.asyncio
async def test_queue_across_worker_instances(_queue_db: Path) -> None:
    q1 = WorkerQueue(max_concurrency=10, db_path=_queue_db)
    await q1.enqueue("cross", {"data": 42}, priority=Priority.NORMAL)
    q2 = WorkerQueue(max_concurrency=10, db_path=_queue_db)
    task = await q2.dequeue()
    assert task is not None
    assert task.type == "cross"
    assert task.payload == {"data": 42}
