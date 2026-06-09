"""Smoke tests for psycopg3 module imports without psycopg2.

The production image ships only psycopg3 (psycopg2 is intentionally
excluded). These tests verify the repository can be imported and
constructed without psycopg2 being installed.

In environments that have psycopg2 installed, these tests are vacuous. In a
production-mimic environment where psycopg2 is hidden, they actively
exercise the production path. Both behaviors are intentional.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest


def test_psycopg3_repository_module_imports() -> None:
    """app.psycopg3_repository must be importable in production environments.

    The base row-codec helpers have been extracted to
    app.postgres_repository_base, so importing app.psycopg3_repository must
    not transitively require psycopg2.
    """
    spec = importlib.util.find_spec("app.psycopg3_repository")
    assert spec is not None, "app.psycopg3_repository should be importable"

    module = importlib.import_module("app.psycopg3_repository")
    # Module must export the expected public surface
    assert hasattr(module, "Psycopg3JobRepository")
    assert hasattr(module, "verify_psycopg3_connectivity")


def test_psycopg3_does_not_import_psycopg2_repository() -> None:
    """app.psycopg3_repository must NOT import from app.postgres_repository.

    The legacy psycopg2 repository file imports psycopg2 at module load time.
    If psycopg3_repository imported from it, the production image (which
    excludes psycopg2) would fail at startup.
    """
    # Read the source to verify no top-level imports from postgres_repository
    import app.psycopg3_repository as mod

    src_file = Path(mod.__file__)
    src = src_file.read_text()
    # Normalize: collapse whitespace for the check
    src_compact = " ".join(src.split())

    forbidden = [
        "from app.postgres_repository import",
        "from app.postgres_repository_base import _conn",
        "from app.postgres_repository_base import _execute",
        "from app.postgres_repository_base import _fetch_all",
        "from app.postgres_repository_base import _fetch_one",
    ]
    for f in forbidden:
        assert f not in src_compact, (
            f"psycopg3_repository must not import {f!r} (would re-introduce psycopg2 dependency in production image)"
        )

    # Shared row-codec helpers must be sourced from postgres_repository_base
    # (which is psycopg-agnostic), not from postgres_repository (psycopg2).
    src_no_strs = " ".join(line for line in src.splitlines() if not line.strip().startswith('"'))
    if "postgres_repository_base" not in src_no_strs and "postgres_repository" in src_no_strs:
        # If any postgres_repository mention exists, it must be the
        # psycopg-agnostic base.
        pytest.fail(
            "psycopg3_repository mentions postgres_repository in source but must only import from postgres_repository_base",
        )


def test_postgres_repository_base_is_psycopg_agnostic() -> None:
    """app.postgres_repository_base must NOT import psycopg2 or psycopg.

    This base module is shared by both psycopg2 and psycopg3 repositories.
    """
    import app.postgres_repository_base as mod

    src_file = Path(mod.__file__)
    src = src_file.read_text()
    src_compact = " ".join(src.split())

    # The base must not import either driver at module load time. The
    # drivers are imported lazily inside the concrete repository
    # implementations, not in the shared base.
    assert "import psycopg2" not in src_compact, "postgres_repository_base must not import psycopg2 (driver-specific)"
    assert "import psycopg" not in src_compact, "postgres_repository_base must not import psycopg (driver-specific)"
    assert "from psycopg" not in src_compact, "postgres_repository_base must not import psycopg (driver-specific)"
    assert "from psycopg2" not in src_compact, "postgres_repository_base must not import psycopg2 (driver-specific)"


def test_postgres_row_codec_helpers_exposed_from_base() -> None:
    """The row-codec helpers (job_to_row, row_to_job, _fetch_all, etc.) should
    be importable from postgres_repository_base, not from the psycopg2-only
    postgres_repository module.
    """
    from app.postgres_repository_base import (
        _fetch_all,
        _fetch_one,
        execute,
        job_to_row,
        row_to_job,
    )

    # These should be callable
    assert callable(job_to_row)
    assert callable(row_to_job)
    assert callable(_fetch_all)
    assert callable(_fetch_one)
    assert callable(execute)
