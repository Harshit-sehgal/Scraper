"""Unit Tests for Phase 85 Shared Geocoding Cache."""

from __future__ import annotations

import contextlib
import os

import pytest
from app.geocode_cache import GeocodeCache


def _clean_cache_db_files(db_path: str) -> None:
    """Remove the geocode cache DB file along with any WAL / SHM journal files."""
    for suffix in ["", "-wal", "-shm", "-journal"]:
        path = db_path + suffix
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)  # noqa: PTH107


@pytest.fixture(autouse=True)
def clean_cache_env(tmp_path):
    # Use a unique DB per test (and per pytest-xdist worker) to avoid
    # cross-process SQLite lock contention when tests run in parallel.
    db_path = str(tmp_path / "geocoding_cache.db")
    _clean_cache_db_files(db_path)
    yield db_path
    _clean_cache_db_files(db_path)


def test_geocode_cache_initialization(clean_cache_env) -> None:
    GeocodeCache(db_path=clean_cache_env)
    assert os.path.exists(clean_cache_env)  # noqa: PTH110


def test_geocode_cache_set_and_get(clean_cache_env) -> None:
    cache = GeocodeCache(db_path=clean_cache_env)

    # Try a query not in the cache (should miss)
    result = cache.get("1600 Amphitheatre Pkwy, Mountain View, CA")
    assert result is None
    assert cache.misses == 1

    # Store entry in cache
    cache.set("1600 Amphitheatre Pkwy, Mountain View, CA", 37.422, -122.084, "Googleplex")

    # Fetch from cache (should hit)
    result = cache.get("1600 Amphitheatre Pkwy, Mountain View, CA")
    assert result is not None
    assert result[0] == 37.422
    assert result[1] == -122.084
    assert result[2] == "Googleplex"
    assert cache.hits == 1
    assert cache.get_hit_rate() == 0.5


def test_negative_caching(clean_cache_env) -> None:
    cache = GeocodeCache(db_path=clean_cache_env)

    # Query negative entry
    cache.set_negative("Invalid Address Here")

    # Querying should hit the negative cache and return specific tag
    result = cache.get("Invalid Address Here")
    assert result is not None
    assert result[0] == 0.0
    assert result[1] == 0.0
    assert result[2] == "EXCLUDED_NEGATIVE_CACHE"
