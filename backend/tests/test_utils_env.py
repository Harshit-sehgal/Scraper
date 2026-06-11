"""Unit tests for the environment parsing helpers in ``app.utils.env``."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.utils.env import env_int


def test_env_int_default_when_unset() -> None:
    """Verify env_int returns default when variable is not set."""
    with patch.dict(os.environ, {}, clear=True):
        assert env_int("TEST_UNSET_VAR", default=42) == 42


def test_env_int_valid_parse() -> None:
    """Verify env_int parses valid integers from string environment values."""
    with patch.dict(os.environ, {"TEST_VALID_VAR": "10"}):
        assert env_int("TEST_VALID_VAR", default=42) == 10


def test_env_int_invalid_fallback() -> None:
    """Verify env_int falls back to default and logs error on invalid strings."""
    with patch.dict(os.environ, {"TEST_INVALID_VAR": "not_an_int"}):
        # Using a patch to prevent spamming output during test
        with patch("app.utils.env.logger.exception") as mock_log:
            assert env_int("TEST_INVALID_VAR", default=42) == 42
            mock_log.assert_called_once()


def test_env_int_minimum_clamp() -> None:
    """Verify env_int clamps parsed values to the specified minimum."""
    with patch.dict(os.environ, {"TEST_MIN_VAR": "5"}):
        assert env_int("TEST_MIN_VAR", default=42, minimum=10) == 10
        assert env_int("TEST_MIN_VAR", default=42, minimum=3) == 5


def test_env_int_maximum_clamp() -> None:
    """Verify env_int clamps parsed values to the specified maximum."""
    with patch.dict(os.environ, {"TEST_MAX_VAR": "20"}):
        assert env_int("TEST_MAX_VAR", default=42, maximum=15) == 15
        assert env_int("TEST_MAX_VAR", default=42, maximum=25) == 20


def test_env_int_min_max_range() -> None:
    """Verify env_int clamps parsed values within a min-max range."""
    with patch.dict(os.environ, {"TEST_RANGE_VAR": "50"}):
        assert env_int("TEST_RANGE_VAR", default=42, minimum=10, maximum=30) == 30

    with patch.dict(os.environ, {"TEST_RANGE_VAR": "5"}):
        assert env_int("TEST_RANGE_VAR", default=42, minimum=10, maximum=30) == 10
