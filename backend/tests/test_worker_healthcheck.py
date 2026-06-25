"""Regression tests for the F-OPSDOC-003 worker healthcheck script.

The script ``scripts/worker_healthcheck.py`` is invoked by Docker
``HEALTHCHECK`` in production compose. Before this fix, no test in
``backend/tests/`` exercised its exit-code contract:

- exit 0 when the DB heartbeat is alive (within TTL)
- exit 1 when the DB heartbeat is stale (older than TTL)
- exit 1 when DB query raises (connectivity outage)
- exit 1 when ``DATAFORGE_WORKER_HEARTBEAT_TTL`` is non-integer or < 1

The tests mock the storage repository via ``app.storage_interface``;
the goal is to lock in the contract, not to verify SQL.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "worker_healthcheck.py"


def _import_script() -> ModuleType:
    """Import ``scripts.worker_healthcheck`` with the script dir on sys.path."""
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    name = "scripts.worker_healthcheck"
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


class _FakeRepo:
    """Stand-in for ``JobRepository.get_worker_health`` that returns canned data."""

    def __init__(self, health: dict[str, object] | None = None, *, exc: Exception | None = None) -> None:
        self.health = health
        self.exc = exc
        self.calls: list[tuple[str, int]] = []

    def __call__(self) -> _FakeRepo:
        # Behaves like a factory that returns itself when used as a factory.
        return self

    # The script imports ``get_job_repository()`` and treats its result as
    # an object with ``get_worker_health``. Wire it together here.
    def get_worker_health(self, worker_id: str, ttl_seconds: int) -> dict[str, object]:
        self.calls.append((worker_id, ttl_seconds))
        if self.exc is not None:
            raise self.exc
        assert self.health is not None
        return self.health


def _patch_repo(monkeypatch, repo: _FakeRepo) -> ModuleType:
    """Patch ``app.storage_interface.get_job_repository`` to return a fake repo wrapper."""
    # Patch the module attribute the script re-imports inside the function.
    from app import storage_interface

    class _RepoWrapper:
        def get_worker_health(self, worker_id: str, ttl_seconds: int) -> dict[str, object]:
            return repo.get_worker_health(worker_id, ttl_seconds)

    wrapper = _RepoWrapper()

    monkeypatch.setattr(storage_interface, "get_job_repository", lambda: wrapper)
    return _import_script()


class TestWorkerHealthcheckServiceContract:
    """The healthcheck returns 0 on healthy, 1 on stale or unreachable."""

    def test_healthy_heartbeat_returns_zero(self, monkeypatch) -> None:
        repo = _FakeRepo({"alive": True, "last_heartbeat": "2026-01-01T00:00:00Z"})
        monkeypatch.setenv("DATAFORGE_WORKER_HEARTBEAT_TTL", "60")
        script = _patch_repo(monkeypatch, repo)

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = script._main()
        assert rc == 0
        assert "HEALTHCHECK FAILED" not in stderr.getvalue()
        assert repo.calls and repo.calls[0][1] == 60

    def test_stale_heartbeat_returns_one(self, monkeypatch) -> None:
        repo = _FakeRepo({"alive": False, "last_heartbeat": "2020-01-01T00:00:00Z"})
        monkeypatch.setenv("DATAFORGE_WORKER_HEARTBEAT_TTL", "60")
        script = _patch_repo(monkeypatch, repo)

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = script._main()
        assert rc == 1
        assert "HEALTHCHECK FAILED" in stderr.getvalue()
        assert "older than 60s" in stderr.getvalue()

    def test_db_query_error_returns_one(self, monkeypatch) -> None:
        repo = _FakeRepo(exc=RuntimeError("connection refused"))
        monkeypatch.setenv("DATAFORGE_WORKER_HEARTBEAT_TTL", "60")
        script = _patch_repo(monkeypatch, repo)

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = script._main()
        assert rc == 1
        assert "db heartbeat check raised" in stderr.getvalue()


class TestWorkerHealthcheckTTLValidation:
    """``DATAFORGE_WORKER_HEARTBEAT_TTL`` must be a positive integer."""

    def test_non_integer_ttl_exits_one(self, monkeypatch) -> None:
        monkeypatch.setenv("DATAFORGE_WORKER_HEARTBEAT_TTL", "not-a-number")
        script = _import_script()
        try:
            script._parse_ttl()
        except SystemExit as exc:
            assert exc.code == 1
        else:
            msg = "_parse_ttl must sys.exit(1) on non-integer TTL"
            raise AssertionError(msg)

    def test_zero_ttl_exits_one(self, monkeypatch) -> None:
        monkeypatch.setenv("DATAFORGE_WORKER_HEARTBEAT_TTL", "0")
        script = _import_script()
        try:
            script._parse_ttl()
        except SystemExit as exc:
            assert exc.code == 1
        else:
            msg = "_parse_ttl must sys.exit(1) on TTL < 1"
            raise AssertionError(msg)

    def test_positive_ttl_returns_int(self, monkeypatch) -> None:
        monkeypatch.delenv("DATAFORGE_WORKER_HEARTBEAT_TTL", raising=False)
        script = _import_script()
        assert script._parse_ttl() == 60
        monkeypatch.setenv("DATAFORGE_WORKER_HEARTBEAT_TTL", "120")
        assert script._parse_ttl() == 120


class TestScriptBootstrapping:
    """The script maintains its runner contract under typical conditions."""

    def test_script_path_exists(self) -> None:
        assert SCRIPT_PATH.is_file(), f"missing healthcheck script at {SCRIPT_PATH}"

    def test_main_function_signature(self) -> None:
        script = _import_script()
        assert callable(getattr(script, "_main", None))
        assert callable(getattr(script, "_parse_ttl", None))
        assert callable(getattr(script, "_check_db_heartbeat", None))
