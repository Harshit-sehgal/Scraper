"""
Unit Tests for Phase 85 Shared Geocoding Cache.
"""

from __future__ import annotations

import os

import pytest
from app.geocode_cache import CACHE_DB_PATH, GeocodeCache, reset_geocode_cache


def _clean_cache_db_files() -> None:
    """Remove the geocode cache DB file along with any WAL / SHM journal files."""
    base = CACHE_DB_PATH
    for suffix in ["", "-wal", "-shm", "-journal"]:
        path = base + suffix
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@pytest.fixture(autouse=True)
def clean_cache_env():
    # Remove existing files if any (including WAL / SHM journal files)
    _clean_cache_db_files()
    reset_geocode_cache()
    yield
    # Cleanup files after test run
    _clean_cache_db_files()
    reset_geocode_cache()


def test_geocode_cache_initialization() -> None:
    GeocodeCache()
    assert os.path.exists(CACHE_DB_PATH)


def test_geocode_cache_set_and_get() -> None:
    cache = GeocodeCache()

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


def test_negative_caching() -> None:
    cache = GeocodeCache()

    # Query negative entry
    cache.set_negative("Invalid Address Here")

    # Querying should hit the negative cache and return specific tag
    result = cache.get("Invalid Address Here")
    assert result is not None
    assert result[0] == 0.0
    assert result[1] == 0.0
    assert result[2] == "EXCLUDED_NEGATIVE_CACHE"
