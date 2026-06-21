import asyncio
import contextlib
import logging
import os
import socket
import sys
import time
from pathlib import Path
from types import ModuleType

import httpx
import pytest

# Setup test environment variables first, before importing any app modules.
ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("DATAFORGE_STATE_FILE", str(ROOT / "backend" / "data" / "jobs_state_test.json"))
os.environ.setdefault("DATAFORGE_DB_CONNECT_TIMEOUT", "1")
os.environ["DATAFORGE_ENV"] = "development"
os.environ["DATAFORGE_ALLOW_INSECURE_DEV_AUTH"] = "true"
os.environ["DATAFORGE_API_KEY"] = ""
os.environ["DATAFORGE_ADMIN_API_KEY"] = ""
os.environ["DATAFORGE_OPERATOR_API_KEY"] = ""
os.environ["DATAFORGE_STORAGE_BACKEND"] = "sqlite"
os.environ.pop("DATAFORGE_DATABASE_URL", None)
os.environ["DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES"] = "true"

from app.models import FieldType, SchemaField

logger = logging.getLogger(__name__)


def pytest_addoption(parser) -> None:
    """Register optional external-service test flags."""
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-postgres",
            action="store_true",
            default=False,
            help="Run tests marked with @pytest.mark.postgres (requires Docker + testcontainers).",
        )
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-golden-dataset",
            action="store_true",
            default=False,
            help="Run golden dataset tests against real websites (requires network).",
        )
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-browser",
            action="store_true",
            default=False,
            help="Run tests marked with @pytest.mark.browser (requires Playwright and local socket binding).",
        )
    with contextlib.suppress(ValueError):
        parser.addoption(
            "--run-hostile-ci-smoke",
            action="store_true",
            default=False,
            help="Run tests marked with @pytest.mark.hostile_ci_smoke against "
            "backend/benchmarks/benchmark_hostile.py (requires Playwright and local socket binding).",
        )


def pytest_configure(config) -> None:
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "postgres: tests that require a running Postgres instance (via testcontainers). Skipped by default.",
    )
    config.addinivalue_line(
        "markers",
        "golden_dataset: tests that hit real websites for extraction validation. Skipped by default (use --run-golden-dataset).",
    )
    config.addinivalue_line(
        "markers",
        "browser: tests that require Playwright/browser runtime and local HTTP server binding. Skipped by default.",
    )
    config.addinivalue_line(
        "markers",
        "hostile_ci_smoke: tests that exercise the live FastAPI benchmark_hostile.py "
        "endpoints (/infinite, /lazy) alongside the JS-resident lazy fixture for "
        "end-to-end hostile-path coverage on CI. Skipped by default "
        "(use --run-hostile-ci-smoke to opt in).",
    )
    config.addinivalue_line(
        "markers",
        (
            "network: tests that intentionally make live DNS/HTTP calls. "
            "The autouse DNS stand-in fixture is bypassed for these tests. "
            "Skipped by default in CI sandboxes without network access."
        ),
    )
    config.addinivalue_line(
        "markers",
        "unit: fast unit tests that must not touch the network, database, or filesystem beyond the test's own tmp dir.",
    )
    config.addinivalue_line(
        "markers",
        "api: API contract tests that exercise the FastAPI app via the in-process ASGI client.",
    )
    config.addinivalue_line(
        "markers",
        "slow: tests whose expected runtime is > 5s. Useful for selective CI tiers.",
    )
    try:
        from testcontainers.postgres import PostgresContainer

        def patched_get_connection_url(self, host=None):
            username = getattr(self, "username", getattr(self, "POSTGRES_USER", "testuser"))
            password = getattr(self, "password", getattr(self, "POSTGRES_PASSWORD", "testpassword"))
            dbname = getattr(self, "dbname", getattr(self, "POSTGRES_DB", "testdb"))
            port = getattr(self, "port", getattr(self, "port_to_expose", 5432))
            driver = getattr(self, "driver", "") or ""
            if driver and not driver.startswith("+"):
                driver = f"+{driver}"
            return self._create_connection_url(
                dialect=f"postgresql{driver}",
                username=username,
                password=password,
                dbname=dbname,
                host="127.0.0.1",
                port=port,
            )

        PostgresContainer.get_connection_url = patched_get_connection_url
    except Exception:  # noqa: RUF100, S110
        pass


def pytest_collection_modifyitems(config, items) -> None:
    skip_postgres = pytest.mark.skip(reason="need --run-postgres to run (Postgres integration tests)")
    skip_golden = pytest.mark.skip(reason="need --run-golden-dataset to run (network-dependent golden dataset validation)")
    skip_browser = pytest.mark.skip(reason="need --run-browser to run (requires Playwright and local socket binding)")
    for item in items:
        if "postgres" in item.keywords and not config.getoption("--run-postgres", default=False):
            item.add_marker(skip_postgres)
        if "golden_dataset" in item.keywords and not config.getoption("--run-golden-dataset", default=False):
            item.add_marker(skip_golden)
        if "browser" in item.keywords and not config.getoption("--run-browser", default=False):
            item.add_marker(skip_browser)
        if "hostile_ci_smoke" in item.keywords and not config.getoption(
            "--run-hostile-ci-smoke",
            default=False,
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason="need --run-hostile-ci-smoke to run (benchmark_hostile.py FastAPI server + Playwright reader)",
                ),
            )


def pytest_sessionfinish(session, exitstatus) -> None:
    """Drain background state writes so pytest exits cleanly after direct module tests."""
    try:
        from app.state_store import flush_state_writes

        flush_state_writes()
    except Exception:  # noqa: RUF100, S110
        pass

    # Clean up test-generated sqlite files, logs, and locks to avoid workspace pollution
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        backend_data = root / "backend" / "data"
        global_data = root / "data"
        logs_dir = root / "logs"

        # List of directories to clean safely
        for p in [backend_data, global_data, logs_dir]:
            if p.exists():
                for item in list(p.glob("**/*")):
                    if (
                        item.is_file()
                        and item.name != ".gitkeep"
                        and any(
                            item.suffix == sfx or str(item.name).endswith(sfx)
                            for sfx in [".db", ".db-journal", ".db-wal", ".db-shm", ".lock", ".log", ".json"]
                        )
                    ):
                        # Ensure we do not delete golden dataset files
                        if "golden_dataset" not in str(item.resolve()):
                            with contextlib.suppress(OSError):
                                item.unlink()
    except Exception:  # noqa: RUF100, S110
        pass

    # ─── Telegram end-of-session summary ──────────────────────────────────
    # The notifier short-circuits silently when TELEGRAM_ENABLED is false
    # or the credentials are missing, so this is always safe to call.
    try:
        stats = getattr(session, "_telegram_stats", None)
        if stats is not None:
            from app.utils.telegram_notifier import get_notifier

            duration = time.monotonic() - stats.get("started_at", time.monotonic())
            notifier = get_notifier()
            if notifier.is_configured:
                result = "PASSED" if stats["failed"] == 0 and exitstatus == 0 else "FAILED"
                notifier.notify_test_end(
                    suite_name=stats["suite_name"],
                    result=result,
                    passed=stats["passed"],
                    failed=stats["failed"],
                    skipped=stats["skipped"],
                    duration_seconds=duration,
                )
    except Exception:  # noqa: RUF100, S110
        pass


# ─── Telegram session-start / per-test / session-finish hooks ─────────────
# These hooks only do work when TELEGRAM_ENABLED is true. The notifier
# itself short-circuits, but we also guard the import so that a
# mis-configured environment cannot break test collection.


def pytest_sessionstart(session) -> None:
    """Send a start-of-session notification (if enabled)."""
    try:
        # Best-effort import: app.config pulls in pydantic-settings and
        # the rest of the settings graph. The notifier itself swallows
        # all errors, but the import must not fail.
        from app.utils.telegram_notifier import get_notifier

        notifier = get_notifier()
    except Exception:
        return

    if not notifier.is_configured:
        return

    # Derive a human-readable suite name from the rootdir / first arg.
    rootdir = str(getattr(session.config, "rootdir", "") or "tests")
    suite_name = f"{Path(rootdir).name} (pytest)"

    session._telegram_stats = {
        "suite_name": suite_name,
        "started_at": time.monotonic(),
        "passed": 0,
        "failed": 0,
        "skipped": 0,
    }
    notifier.notify_test_start(suite_name)


def pytest_runtest_logreport(report) -> None:
    """Track per-test outcomes and notify on individual failures."""
    if report.when != "call":
        return
    try:
        from app.utils.telegram_notifier import get_notifier

        notifier = get_notifier()
    except Exception:
        return

    session = getattr(report, "session", None)
    stats = getattr(session, "_telegram_stats", None) if session is not None else None

    if report.outcome == "failed":
        if stats is not None:
            stats["failed"] += 1
        if notifier.is_configured:
            # report.longrepr is None for some non-test failures; guard.
            error = str(report.longrepr) if report.longrepr else "<no longrepr>"
            notifier.notify_test_failure(report.nodeid, error)
    elif report.outcome == "skipped":
        if stats is not None:
            stats["skipped"] += 1
    elif report.outcome == "passed":
        if stats is not None:
            stats["passed"] += 1


main_mod: ModuleType | None = None
try:
    import app.main

    main_mod = app.main
except ImportError as e:
    import warnings

    warnings.warn(f"Could not import app.main (tests requiring the client fixture will fail): {e}", stacklevel=2)


# Pre-import ``app.services.state`` so the conftest's monkeypatch.setattr
# string path ``app.services.state.persist_state`` resolves deterministically.
# ``app.services`` is a namespace package (no ``__init__.py``) and
# ``app.main`` does not transitively import ``app.services.state``; without
# this pre-import, the ``client`` fixture below can fail with
# ``AttributeError: module 'app.services' has no attribute 'state'`` in
# full-suite collection order (PR review, 2026-06).
with contextlib.suppress(ImportError):
    import app.services.state


# ─── DNS isolation (Phase 0, M1) ────────────────────────────────────────────
# This autouse fixture replaces ``socket.getaddrinfo`` with a deterministic
# stand-in for every test that is not explicitly marked ``network`` or
# ``integration``. The stand-in maps a small, fixed set of test hostnames
# to deterministic IPs (matching the pattern already proven in
# ``test_production_hardening.py::mock_dns_resolution``) and resolves any
# other hostname to a public IP. Real DNS is therefore not exercised by
# unmarked unit/API tests, which is the Phase 0 acceptance gate:
#
#   "No unmarked unit/API test performs real DNS or live internet access."
#
# Tests that intentionally need real DNS must declare ``@pytest.mark.network``
# (or ``@pytest.mark.integration``). The stand-in fixture inspects
# ``request.keywords`` and yields the original ``socket.getaddrinfo`` for
# those tests, leaving the system in its native state.
#
# Notes on layering:
# * The fixture is function-scoped and is run before the test body, so a
#   test that does its own ``monkeypatch.setattr(socket, "getaddrinfo", ...)``
#   inside the test still takes effect: pytest's monkeypatch is restored
#   at test teardown, and the autouse fixture re-arms the stand-in for the
#   next test.
# * Existing per-file autouse fixtures (e.g. ``mock_dns_resolution`` in
#   ``test_production_hardening.py``) override the conftest's stand-in
#   because they also run inside the test setup phase and replace
#   ``socket.getaddrinfo``. Both layers co-exist safely because each test
#   only sees one stand-in at a time.

_PUBLIC_STANDIN_IPV4 = "8.8.8.8"
_PUBLIC_STANDIN_IPV6 = "2001:4860:4860::8888"
_LOOPBACK_HOSTS = frozenset({"localhost", "ip6-localhost", "ip6-loopback"})
_LOOPBACK_IPV4 = "127.0.0.1"
_LOOPBACK_IPV6 = "::1"
_PRIVATE_HOSTS = frozenset({"nginx", "smoke-host", "host.docker.internal"})
_PRIVATE_IPV4 = "172.16.0.2"
_METADATA_HOSTS = frozenset({"169.254.169.254", "metadata.google.internal", "instance-data"})


def _dns_standin(original):
    """Return a ``getaddrinfo``-shaped function that never calls the OS.

    The returned function is intentionally conservative: it returns a
    well-formed record for any input, so callers like
    ``validate_public_http_url`` can complete their SSRF checks without
    raising ``gaierror``. Hosts that are explicitly loopback/private are
    mapped to their canonical ranges so the safety checks still fire.
    """

    def stub(host, port, *args, **kwargs):
        # Numeric inputs (IPv4 / IPv6 strings) are forwarded so that
        # existing tests asserting on numeric hosts keep working.
        if isinstance(host, str) and host:
            if host in _LOOPBACK_HOSTS:
                return [
                    (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (_LOOPBACK_IPV6, port or 0, 0, 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", (_LOOPBACK_IPV4, port or 0)),
                ]
            if host in _PRIVATE_HOSTS:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PRIVATE_IPV4, port or 0))]
            if host in _METADATA_HOSTS:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port or 0))]
            if host in (_LOOPBACK_IPV4, _LOOPBACK_IPV6):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port or 0))]
            # Public hostnames map to a fixed public IP so SSRF safety
            # checks pass without leaking the actual A record.
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (_PUBLIC_STANDIN_IPV6, port or 0, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_STANDIN_IPV4, port or 0)),
            ]
        # Non-string (None, etc.) falls through to the original.
        return original(host, port, *args, **kwargs)

    return stub


@pytest.fixture(autouse=True)
def _default_dns_resolver(request, monkeypatch):
    """Install the conftest-level DNS stand-in unless the test opted out.

    Opt-out markers: ``network`` and ``integration``. The original
    ``socket.getaddrinfo`` is left untouched for those tests, so a test
    that needs real DNS will see real DNS. The fixture is function-scoped
    so a test's own ``monkeypatch.setattr(socket, "getaddrinfo", ...)``
    inside the body still takes precedence for the duration of that test.
    """
    keywords = getattr(request, "keywords", {}) or {}
    if "network" in keywords or "integration" in keywords:
        yield
        return
    try:
        import socket as _socket
    except ImportError:  # pragma: no cover - impossible in CPython
        yield
        return
    original = _socket.getaddrinfo
    monkeypatch.setattr(_socket, "getaddrinfo", _dns_standin(original))
    yield


@pytest.fixture(autouse=True)
def reset_semantic_world_state():
    try:
        from app.semantic_world_state import reset_world_state

        reset_world_state()
    except ImportError:
        pass
    yield
    try:
        from app.semantic_world_state import reset_world_state

        reset_world_state()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_failure_injection():
    from app.failure_injector import set_injection_probability

    set_injection_probability(0.0)
    yield
    set_injection_probability(0.0)


@pytest.fixture(autouse=True)
def reset_queue():
    try:
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
    except ImportError:
        pass
    yield
    try:
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _disable_telegram_in_tests(monkeypatch):
    """Force-disable Telegram notifications for every test.

    This is a belt-and-suspenders guard. The notifier already
    short-circuits when TELEGRAM_ENABLED is false or credentials are
    missing, but this fixture ensures no test run can accidentally
    trigger a real Telegram API call regardless of env-var leakage
    or settings drift.

    P1-TESTNET-001 (Prompt 0-4 remaining task): the Phase 0 audit
    observed an SSL error to api.telegram.org during one full-suite
    pytest run. That specific failure is not currently reproducible,
    but this fixture makes the safeguard explicit and testable.
    """
    # Clear every Telegram env var that the notifier might read.
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ENABLED",
        "TELEGRAM_TOKEN",
        "TELEGRAM_TO",
        "TELEGRAM_NOTIFICATIONS_ENABLED",
        "TELEGRAM_ENABLE_NOTIFICATIONS",
        "DATAFORGE_TELEGRAM_BOT_TOKEN",
        "DATAFORGE_TELEGRAM_CHAT_ID",
        "DATAFORGE_TELEGRAM_ENABLED",
        "DATAFORGE_TELEGRAM_API_BASE",
    ):
        monkeypatch.delenv(var, raising=False)

    # Reset the module-level notifier caches and patch the
    # app.services.notifications singleton so both notifier
    # modules see the cleared state. The app.utils.telegram_notifier
    # module reads env vars directly via os.getenv (already cleared
    # above), so only the app.services.notifications singleton needs
    # explicit instance patching.
    try:
        from app.utils.telegram_notifier import reset_notifier

        reset_notifier()
    except ImportError:
        pass
    try:
        from app.services.notifications import get_telegram_notifier

        n = get_telegram_notifier()
        monkeypatch.setattr(n, "enabled", False)
        monkeypatch.setattr(n, "token", "")
        monkeypatch.setattr(n, "chat_id", "")
    except ImportError:
        pass

    yield

    # Restore caches at teardown so the next test starts clean.
    try:
        from app.utils.telegram_notifier import reset_notifier

        reset_notifier()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_lifespan_state_fixture():
    """Reset the module-level lifespan state before and after each test.

    Mirrors the pattern of ``reset_queue`` / ``reset_failure_injection``:
    we call ``reset_lifespan_state()`` at fixture entry to clear any
    cached ``job_repo`` / ``gossip`` / ``heartbeat_mgr`` from a previous
    test, and again at teardown so a subsequent test in the same
    process starts clean. The helper itself is a test-only backstop
    (see ``app.lifespan.reset_lifespan_state``); production code does
    not call it.
    """
    try:
        from app.lifespan import reset_lifespan_state

        reset_lifespan_state()
    except ImportError:
        pass
    yield
    try:
        from app.lifespan import reset_lifespan_state

        reset_lifespan_state()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def reset_usage_ledger_fixture():
    """Reset the global usage ledger before each test.

    The usage ledger stores per-user quotas (e.g. job creation limits).
    Without reset, an earlier test can exhaust a quota and cause false
    429 failures in later tests.
    """
    try:
        from app.utils.usage_ledger import reset_usage_ledger

        reset_usage_ledger()
    except ImportError:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_identity_store_fixture():
    """Reset the SaaS identity store between tests.

    The identity store's SQLite DB persists across test boundaries because
    it is file-backed. Without clearing, earlier tests can create users or
    orgs that cause unique-constraint or state conflicts in later tests.

    Also resets the SaaS router's in-memory rate limiter counters so
    rapid test requests from the same loopback IP don't trigger 429s.
    """
    try:
        import sqlite3

        from app.saas.identity_store import get_identity_store, reset_identity_store

        try:
            store = get_identity_store()
            with store._connect() as conn:  # type: ignore[attr-defined]
                for table in ("api_keys", "projects", "memberships", "organizations", "users"):
                    with contextlib.suppress(sqlite3.OperationalError):
                        conn.execute(f"DELETE FROM {table}")
                conn.commit()
        except Exception:
            logger.debug("Identity store cleanup failed (non-critical)", exc_info=True)

        reset_identity_store()
    except ImportError:
        pass

    # Reset SaaS rate limiters so tests running from the same IP don't 429
    try:
        from app.saas.router import reset_rate_limiters

        reset_rate_limiters()
    except ImportError:
        pass


# ─── Helper functions ──────────────────────────────────────────────────────


def make_schema_field_list(names: list[str], field_type: FieldType = FieldType.STRING) -> list[SchemaField]:
    """Helper to create SchemaField lists from field names. Shared across test files."""
    return [SchemaField(name=n, field_type=field_type, required=False, description="") for n in names]


class LocalASGIClient:
    """Small sync wrapper around httpx ASGITransport that avoids TestClient threads.

    Uses a single persistent event loop rather than calling ``asyncio.run()``
    per request, which avoids ResourceWarnings from sockets that outlive a
    short-lived loop.
    """

    def __init__(self, app) -> None:
        self.app = app
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

    def close(self) -> None:
        """Shut down the persistent event loop and release resources.

        Note: ``asyncio.all_tasks()`` is deliberately not called here because
        its ``loop`` parameter was removed in Python 3.12 and the httpx
        ``AsyncClient`` context manager in ``_request()`` already handles
        proper socket cleanup.
        """
        try:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        finally:
            self._loop.close()
            asyncio.set_event_loop(None)

    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        cookies = kwargs.pop("cookies", None)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", cookies=cookies) as client:
            return await client.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs):
        return self._loop.run_until_complete(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


@pytest.fixture
def client(monkeypatch):
    async def fake_run_job(job_id: str, **kwargs) -> None:
        # Keep jobs in pending state unless a test explicitly changes them.
        await asyncio.sleep(0.01)

    def fake_schedule_background_task(coro):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                return loop.create_task(coro)
        except RuntimeError:
            pass
        return None

    # Avoid writing persistence files in API unit tests. We resolve the
    # module through a direct import (cached at conftest load) rather than
    # a string path, so the patch is robust to ``app.services.state`` not
    # being in ``sys.modules`` at fixture time.
    from app.services import state as _app_services_state_mod

    monkeypatch.setattr(_app_services_state_mod, "persist_state", lambda **kwargs: None)
    # Swap runtime deps so route handlers see the fake implementations
    # instead of the real job runner/scheduler. This is the A1 fix:
    # routes reference ``app.runtime_deps.schedule_task_fn`` and
    # ``app.runtime_deps.run_job_coro_fn`` at call time, not captured
    # closures, so the swap is effective immediately.
    import app.runtime_deps as _runtime_deps_mod

    monkeypatch.setattr(
        _runtime_deps_mod,
        "schedule_task_fn",
        fake_schedule_background_task,
    )
    monkeypatch.setattr(
        _runtime_deps_mod,
        "run_job_coro_fn",
        fake_run_job,
    )
    # Also keep the old monkeypatches for backward compat with code that
    # imports these directly from app.main.
    monkeypatch.setattr(main_mod, "run_job", fake_run_job)
    monkeypatch.setattr("app.lifespan.run_job", fake_run_job)
    monkeypatch.setattr(main_mod, "_schedule_background_task", fake_schedule_background_task)

    assert main_mod is not None

    # Disable API-key auth and metrics-token auth for unit tests. Local
    # tests run against a fresh in-process app and the dev escape hatch in
    # ``rbac.get_current_role`` requires ``ALLOW_INSECURE_DEV_AUTH=True`` to
    # take effect when ``DATAFORGE_ENV=development``. Setting the env var
    # before settings is read also avoids depending on .env values.
    monkeypatch.setattr(main_mod.settings, "API_KEY", "")
    monkeypatch.setattr(main_mod.settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(main_mod.settings, "OPERATOR_API_KEY", "")
    monkeypatch.setattr(main_mod.settings, "METRICS_TOKEN", "")
    monkeypatch.setattr(main_mod.settings, "ALLOW_INSECURE_DEV_AUTH", True)
    # ENABLE_EXPERIMENTAL_ROUTES is set at conftest import time (see
    # ``os.environ.setdefault`` above) so the experimental router is
    # already mounted on ``app``. The settings attribute override
    # below is kept for tests that re-import app.main with the
    # flag off — they need it re-enabled for the client fixture.
    monkeypatch.setattr(main_mod.settings, "ENABLE_EXPERIMENTAL_ROUTES", True)

    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()

    # Reset rate limiter counters so rapid test requests don't trigger 429s
    if hasattr(main_mod, "rate_limiter"):
        main_mod.rate_limiter.reset()

    # Clear idempotency keys so tests don't see stale records from previous runs
    try:
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute("DELETE FROM idempotency_keys")
                conn.commit()
            finally:
                conn.close()
    except Exception:  # noqa: RUF100, S110
        pass

    client = LocalASGIClient(main_mod.app)
    yield client

    client.close()
    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()
    try:
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                conn.execute("DELETE FROM idempotency_keys")
                conn.commit()
            finally:
                conn.close()
    except Exception:  # noqa: RUF100, S110
        pass


@pytest.fixture
def auth_headers() -> dict:
    """Empty auth headers — API key auth is disabled in tests via conftest."""
    return {}


@pytest.fixture
def operator_headers() -> dict:
    """Empty operator headers — operator auth is disabled in tests via conftest."""
    return {}


@pytest.fixture
def clean_db():
    """Clear job/recycle stores and identity DB for a clean test state."""
    import app.main as main_mod
    from app.job_store import _DB_LOCK, _get_connection

    main_mod.jobs_store.clear()
    main_mod.recycle_bin_store.clear()
    try:
        with _DB_LOCK:
            conn = _get_connection()
            conn.execute("DELETE FROM idempotency_keys")
            conn.commit()
            conn.close()
    except Exception:
        pass
    from app.utils.usage_ledger import reset_usage_ledger

    reset_usage_ledger()
    from app.saas.router import reset_rate_limiters

    reset_rate_limiters()
    yield


@pytest.fixture
def session_client(monkeypatch):
    """TestClient pre-authenticated with an admin session cookie."""
    from app import main as main_mod
    from app.auth.session import SESSION_COOKIE, create_session_cookie
    from fastapi.testclient import TestClient

    monkeypatch.setattr(main_mod.settings, "API_KEY", "")
    monkeypatch.setattr(main_mod.settings, "ADMIN_API_KEY", "")
    monkeypatch.setattr(main_mod.settings, "OPERATOR_API_KEY", "")
    monkeypatch.setattr(main_mod.settings, "METRICS_TOKEN", "")
    monkeypatch.setattr(main_mod.settings, "ALLOW_INSECURE_DEV_AUTH", True)

    cookies = {SESSION_COOKIE: create_session_cookie(role="admin", user_id="test-admin-id")}
    client = TestClient(main_mod.app, cookies=cookies)
    client.session = {"user_id": "test-admin-id", "role": "admin"}
    return client
