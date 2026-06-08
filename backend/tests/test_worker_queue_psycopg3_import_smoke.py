"""Smoke tests for the psycopg3 worker queue.

Verifies that the Postgres worker queue can be constructed via the
factory using psycopg 3 without requiring ``psycopg2`` to be installed
(production-mimic). The legacy ``psycopg2`` driver remains the dev
default but must NOT be the only path.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path


def test_worker_queue_psycopg3_module_imports() -> None:
    """The psycopg3 worker queue module must be importable."""
    spec = importlib.util.find_spec("app.worker_queue_postgres_psycopg3")
    assert spec is not None, "app.worker_queue_postgres_psycopg3 should be importable"
    module = importlib.import_module("app.worker_queue_postgres_psycopg3")
    assert hasattr(module, "PostgresWorkerQueuePsycopg3")


def test_worker_queue_base_module_imports() -> None:
    """The driver-agnostic base module must be importable."""
    spec = importlib.util.find_spec("app.worker_queue_postgres_base")
    assert spec is not None, "app.worker_queue_postgres_base should be importable"
    module = importlib.import_module("app.worker_queue_postgres_base")
    assert hasattr(module, "PostgresWorkerQueueBase")
    assert hasattr(module, "get_postgres_worker_queue_base")
    assert hasattr(module, "reset_postgres_worker_queue_base")


def test_worker_queue_base_is_psycopg_agnostic() -> None:
    """The base module must NOT import psycopg2 or psycopg at module load time.

    The drivers are imported lazily inside the concrete queue
    implementations, not in the shared base.
    """
    import app.worker_queue_postgres_base as mod

    src_file = Path(mod.__file__)
    src = src_file.read_text()
    top_level = "\n".join(_get_top_level_imports(src))

    assert "import psycopg2" not in top_level, "worker_queue_postgres_base must not import psycopg2"
    assert "from psycopg2" not in top_level, "worker_queue_postgres_base must not import psycopg2"
    assert "import psycopg" not in top_level, "worker_queue_postgres_base must not import psycopg"
    assert "from psycopg" not in top_level, "worker_queue_postgres_base must not import psycopg"


def test_postgres_worker_queue_psycopg3_is_subclass_of_base() -> None:
    """The psycopg3 queue must inherit from the shared base class."""
    from app.worker_queue_postgres_base import PostgresWorkerQueueBase
    from app.worker_queue_postgres_psycopg3 import PostgresWorkerQueuePsycopg3

    assert issubclass(PostgresWorkerQueuePsycopg3, PostgresWorkerQueueBase)


def test_postgres_worker_queue_psycopg2_is_subclass_of_base() -> None:
    """The legacy psycopg2 queue must also inherit from the shared base class."""
    from app.worker_queue_postgres import PostgresWorkerQueue
    from app.worker_queue_postgres_base import PostgresWorkerQueueBase

    assert issubclass(PostgresWorkerQueue, PostgresWorkerQueueBase)


def _get_top_level_imports(src: str) -> list[str]:
    """Return all module-level (top-level) import statements in *src*.

    Skips imports inside function bodies — those are lazy and acceptable.
    """
    import ast

    tree = ast.parse(src)
    top_level_imports: list[str] = []
    for node in tree.body:  # iterate only module-level statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_imports.append(f"import {alias.name}")  # noqa: PERF401
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                top_level_imports.append(f"from {module} import {alias.name}")  # noqa: PERF401
    return top_level_imports


def test_postgres_worker_queue_psycopg3_does_not_import_psycopg2() -> None:
    """The psycopg3 queue must NOT import psycopg2 at module load time."""
    import app.worker_queue_postgres_psycopg3 as mod

    src_file = Path(mod.__file__)
    src = src_file.read_text()
    top_level = "\n".join(_get_top_level_imports(src))

    assert "import psycopg2" not in top_level, "psycopg3 module must not import psycopg2 at top level"
    assert "from psycopg2" not in top_level, "psycopg3 module must not import psycopg2 at top level"


def test_psycopg2_queue_uses_lazy_psycopg2_imports() -> None:
    """The psycopg2 queue must not import psycopg2 at module load time.

    This lets the module be importable in psycopg2-blocked environments
    (production-mimic) so the dispatcher can still function.
    """
    import app.worker_queue_postgres as mod

    src_file = Path(mod.__file__)
    src = src_file.read_text()
    top_level = "\n".join(_get_top_level_imports(src))

    assert "import psycopg2" not in top_level, "psycopg2 queue must use lazy psycopg2 import"
    assert "from psycopg2" not in top_level, "psycopg2 queue must use lazy psycopg2 import"
