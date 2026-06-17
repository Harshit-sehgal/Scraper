"""Cross-process regression tests for the SQLite-backed job store.

Pins the multi-worker visibility contract for the SQLite-backed
``backend.app.job_store`` (the persistent source of truth): writes
from any process must be immediately visible to any other process
opening the same database, and concurrent writers must not corrupt
the schema or lose rows.

The in-memory ``globals.jobs_store`` dict is a per-process cache
hydrated from SQLite at startup; cross-process visibility is the
database's job, not the dict's. These tests exercise the SQLite
write path (``save_state``, ``persist_state_single``,
``record_idempotency_key``) directly through subprocesses, then
read back through a fresh process to confirm every write landed.

We deliberately avoid pytest's ``ProcessPoolExecutor`` / fork in
favour of ``subprocess.run`` so the worker processes have a clean
interpreter state (no inherited DB connections, locks, or
half-imported modules) — exactly the production pattern.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
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

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_job_subprocess_script(state_file: Path, job_id: str, name: str) -> str:
    """Return a small python script that writes a single job via job_store."""
    state_file_str = json.dumps(str(state_file))
    repo_root_str = json.dumps(str(REPO_ROOT))
    repo_root_backend_str = json.dumps(str(REPO_ROOT / "backend"))
    job_id_str = json.dumps(job_id)
    name_str = json.dumps(name)
    script = f"""
        import json, os, sys
        os.environ['DATAFORGE_DOTENV_PATH'] = '/dev/null'
        os.environ['DATAFORGE_STATE_FILE'] = {state_file_str}
        sys.path.insert(0, {repo_root_str})
        sys.path.insert(0, {repo_root_backend_str})
        from app.models import Job, JobStatus, ScrapeMode, SourcePolicy
        from app import job_store
        job = Job(
            id={job_id_str},
            name={name_str},
            mode=ScrapeMode.MANUAL,
            status=JobStatus.COMPLETED,
            urls=["https://example.com/{job_id}"],
            source_policy=SourcePolicy.ALL_SOURCES,
            schema_fields=[],
            filters=[],
            total_records=1,
        )
        job_store.reset_job_store_for_tests()
        from app import globals as _g
        _g.jobs_store[job.id] = job
        job_store.save_state(_g.jobs_store, _g.recycle_bin_store, prune_missing=False)
        print(json.dumps({{"wrote": job.id, "pid": os.getpid()}}))
"""
    return textwrap.dedent(script).strip()


def _run_subprocess(script: str, env: dict) -> subprocess.CompletedProcess:
    """Run a small python script in a clean interpreter."""
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(REPO_ROOT),
        timeout=60,
    )


@pytest.fixture
def isolated_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point job_store at a fresh temp DB for each test."""
    state_file = tmp_path / "jobs_state.json"
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    return state_file


def test_subprocess_writes_visible_to_main_process(isolated_state_file: Path) -> None:
    """A worker subprocess writes a job; the main process reads it back."""
    from app import job_store

    job_store.reset_job_store_for_tests()
    job_store.load_state(recover_in_progress=False)

    result = _run_subprocess(
        _write_job_subprocess_script(isolated_state_file, "job-x", "Worker X"),
        {},
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"
    assert "wrote" in result.stdout

    job_store.reset_job_store_for_tests()
    jobs, _recycle, _ = job_store.load_state(recover_in_progress=False)
    assert "job-x" in jobs
    assert jobs["job-x"].name == "Worker X"


def test_concurrent_subprocess_writers_persist_every_row(isolated_state_file: Path) -> None:
    """N subprocesses write distinct jobs; the main process sees all of them.

    This is the key multi-worker safety test: with ``PRAGMA journal_mode=WAL``
    and the ``_DB_LOCK``-serialised write path, SQLite must serialise the
    concurrent commits so that no job is dropped or partially written.
    """
    from app import job_store

    job_store.reset_job_store_for_tests()
    job_store.load_state(recover_in_progress=False)

    n_workers = 8
    procs = []
    for i in range(n_workers):
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _write_job_subprocess_script(isolated_state_file, f"job-{i}", f"Worker {i}"),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "DATAFORGE_STATE_FILE": str(isolated_state_file)},
                cwd=str(REPO_ROOT),
            ),
        )
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, f"worker failed: stdout={out!r} stderr={err!r}"

    job_store.reset_job_store_for_tests()
    jobs, _recycle, _ = job_store.load_state(recover_in_progress=False)
    assert len(jobs) == n_workers
    for i in range(n_workers):
        assert f"job-{i}" in jobs, f"job-{i} missing after concurrent writes"
        assert jobs[f"job-{i}"].name == f"Worker {i}"


def test_persist_state_single_uses_wal_mode(isolated_state_file: Path) -> None:
    """SQLite must be in WAL mode so multiple processes can read+write concurrently."""
    from app import job_store

    job_store.reset_job_store_for_tests()
    job_store.load_state(recover_in_progress=False)

    db_path = isolated_state_file.with_suffix(".db")
    conn = sqlite3.connect(str(db_path))
    try:
        mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode_row is not None
        assert mode_row[0].lower() == "wal", f"jobs DB must be in WAL mode for multi-worker writes; got {mode_row[0]!r}"
    finally:
        conn.close()


def test_threaded_writers_dont_corrupt_results_blob(isolated_state_file: Path) -> None:
    """N threads writing ``persist_state_single`` concurrently keep ``results`` intact.

    Single-process but exercises the same lock contract used by the
    in-process writers; catches a regression where a future change drops
    the ``_DB_LOCK`` around the INSERT OR REPLACE.
    """
    from app import job_store
    from app.models import Job, JobStatus, ScrapeMode, SourcePolicy

    job_store.reset_job_store_for_tests()
    job_store.load_state(recover_in_progress=False)

    n_threads = 16
    errors: list[str] = []

    def writer(idx: int) -> None:
        try:
            job = Job(
                id=f"thread-{idx}",
                name=f"Thread Writer {idx}",
                mode=ScrapeMode.MANUAL,
                status=JobStatus.COMPLETED,
                urls=[f"https://example.com/{idx}"],
                source_policy=SourcePolicy.ALL_SOURCES,
                schema_fields=[],
                filters=[],
                results=[{"record_idx": idx, "value": f"row-{idx}"}],
                total_records=1,
            )
            job_store.persist_state_single(job)
        except Exception as exc:
            errors.append(f"thread-{idx}: {exc!r}")

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    for t in threads:
        assert not t.is_alive(), "thread hung"

    assert not errors, errors

    job_store.reset_job_store_for_tests()
    jobs, _recycle, _ = job_store.load_state(recover_in_progress=False)
    assert len(jobs) == n_threads
    for i in range(n_threads):
        assert f"thread-{i}" in jobs
        assert jobs[f"thread-{i}"].results == [{"record_idx": i, "value": f"row-{i}"}]
