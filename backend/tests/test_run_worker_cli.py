"""Regression tests for ``scripts/run_worker.py`` CLI behavior."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util as importlib_util
import signal
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_worker.py"
BACKEND_PATH = (REPO_ROOT / "backend").resolve()


def _import_script() -> ModuleType:
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    parent_name = "scripts"
    if parent_name not in sys.modules:
        parent_module = ModuleType(parent_name)
        parent_module.__path__ = [scripts_dir]
        sys.modules[parent_name] = parent_module

    module_name = "scripts.run_worker"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])

    spec = importlib_util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None, f"could not load spec for {SCRIPT_PATH}"
    module = importlib_util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeQueue:
    def __init__(self) -> None:
        self.max_concurrency: int | None = None
        self.handlers: dict[str, object] = {}
        self._handlers: dict[str, object] = {}
        self.dequeue_timeouts: list[float] = []
        self.started = False
        self.stopped_with_drain: bool | None = None

    def set_max_concurrency(self, workers: int) -> None:
        self.max_concurrency = workers

    def register_handler(self, name: str, handler: object) -> None:
        self.handlers[name] = handler
        self._handlers[name] = handler

    async def start(self) -> None:
        self.started = True

    async def stop(self, *, drain: bool) -> None:
        self.stopped_with_drain = drain

    def get_poll_interval(self) -> float:
        return 0.25

    async def dequeue(self, *, timeout: float) -> object | None:
        self.dequeue_timeouts.append(timeout)
        return None

    async def fail(self, task_id: str, error: str, *, retry: bool) -> None:
        msg = f"unexpected fail call: {task_id=} {error=} {retry=}"
        raise AssertionError(msg)

    async def complete(self, task_id: str, result: object) -> None:
        msg = f"unexpected complete call: {task_id=} {result=}"
        raise AssertionError(msg)


class _HeartbeatRecorder:
    instances: list[_HeartbeatRecorder] = []

    def __init__(self, *, interval: float, ttl: float) -> None:
        self.interval = interval
        self.ttl = ttl
        self.started = False
        self.stopped = False
        self.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _patch_worker_queue(monkeypatch, queue: _FakeQueue) -> None:
    from app import worker_queue

    monkeypatch.setattr(worker_queue, "get_worker_queue", lambda: queue)


def _patch_heartbeat(monkeypatch, heartbeat_cls: type) -> None:
    heartbeat_module = ModuleType("app.worker_heartbeat")
    heartbeat_module.HeartbeatManager = heartbeat_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.worker_heartbeat", heartbeat_module)


def _run_main(monkeypatch, script: ModuleType, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), *argv])
    asyncio.run(script.main())


class TestRunWorkerPathBootstrap:
    """Importing the script wires the backend tree onto ``sys.path``."""

    def test_import_adds_backend_directory_to_python_path(self) -> None:
        saved_path = list(sys.path)
        try:
            sys.path = [path for path in sys.path if Path(path or ".").resolve() not in {REPO_ROOT.resolve(), BACKEND_PATH}]
            _import_script()
            resolved = {Path(path or ".").resolve() for path in sys.path}
            assert BACKEND_PATH in resolved
        finally:
            sys.path = saved_path

    def test_module_loads_without_runtime_error(self) -> None:
        script = _import_script()
        assert callable(script.main)
        assert callable(script.scrape_job_handler)


class TestRunWorkerSubprocessCLI:
    """Subprocess coverage for public argparse behavior."""

    def test_script_help_exits_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"scripts/run_worker.py --help crashed: stderr={proc.stderr!r}"
        for flag in ("--workers", "--once", "--drain-timeout", "--heartbeat-interval", "--heartbeat-ttl"):
            assert flag in proc.stdout

    def test_unknown_flag_exits_nonzero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--no-such-flag"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode != 0
        assert "unrecognized" in proc.stderr.lower() or "usage" in proc.stderr.lower()


class TestRunWorkerOnceMode:
    """``--once`` drains queued work and skips the heartbeat manager."""

    def test_once_mode_configures_queue_and_skips_heartbeat(self, monkeypatch) -> None:
        script = _import_script()
        queue = _FakeQueue()
        _patch_worker_queue(monkeypatch, queue)

        class _UnexpectedHeartbeat:
            def __init__(self, *args: object, **kwargs: object) -> None:
                msg = "HeartbeatManager must not be constructed in --once mode"
                raise AssertionError(msg)

        _patch_heartbeat(monkeypatch, _UnexpectedHeartbeat)

        _run_main(
            monkeypatch,
            script,
            ["--workers", "7", "--once", "--drain-timeout", "0.01"],
        )

        assert queue.max_concurrency == 7
        assert "scrape_job" in queue.handlers
        assert queue.started is True
        assert queue.stopped_with_drain is True
        assert queue.dequeue_timeouts == [2.0]


class TestRunWorkerContinuousMode:
    """Continuous mode starts heartbeat and registers shutdown signals."""

    def test_continuous_mode_uses_heartbeat_args_and_signal_handlers(self, monkeypatch) -> None:
        script = _import_script()
        queue = _FakeQueue()
        _patch_worker_queue(monkeypatch, queue)
        _HeartbeatRecorder.instances.clear()
        _patch_heartbeat(monkeypatch, _HeartbeatRecorder)

        class _FakeEvent:
            instances: list[_FakeEvent] = []

            def __init__(self) -> None:
                self.set_calls = 0
                self.instances.append(self)

            def set(self) -> None:
                self.set_calls += 1

            async def wait(self) -> None:
                return None

        class _FakeLoop:
            def __init__(self) -> None:
                self.handlers: dict[signal.Signals, Callable[[], None]] = {}

            def add_signal_handler(self, sig: signal.Signals, callback: Callable[[], None]) -> None:
                self.handlers[sig] = callback

        fake_loop = _FakeLoop()
        monkeypatch.setattr(script.asyncio, "Event", _FakeEvent)
        monkeypatch.setattr(script.asyncio, "get_running_loop", lambda: fake_loop)

        _run_main(
            monkeypatch,
            script,
            ["--workers", "2", "--heartbeat-interval", "0.5", "--heartbeat-ttl", "3"],
        )

        assert queue.max_concurrency == 2
        assert queue.started is True
        assert queue.stopped_with_drain is True
        assert set(fake_loop.handlers) == {signal.SIGINT, signal.SIGTERM}

        heartbeat = _HeartbeatRecorder.instances[-1]
        assert heartbeat.interval == 0.5
        assert heartbeat.ttl == 3.0
        assert heartbeat.started is True
        assert heartbeat.stopped is True

        event = _FakeEvent.instances[-1]
        fake_loop.handlers[signal.SIGTERM]()
        assert event.set_calls == 1
