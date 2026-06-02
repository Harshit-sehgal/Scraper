"""Unit tests for production startup security gates (prod_security_validator.py)."""

from __future__ import annotations

import os

import pytest
from app.utils.prod_security_validator import validate_production_credentials


class MockSettings:
    """Mock Settings class for Pydantic-like settings objects."""

    def __init__(
        self,
        env: str = "development",
        api_key: str = "",
        operator_api_key: str = "",
        admin_api_key: str = "",
        storage_backend: str = "sqlite",
        database_url: str = "",
    ):
        self.ENV = env
        self.API_KEY = api_key
        self.OPERATOR_API_KEY = operator_api_key
        self.ADMIN_API_KEY = admin_api_key
        self.STORAGE_BACKEND = storage_backend
        self.DATABASE_URL = database_url


def test_validator_does_nothing_in_development():
    """Verify that validator passes immediately without error in development mode, even with weak keys."""
    settings = MockSettings(
        env="development",
        api_key="change-me",
        operator_api_key="dev-key",
        admin_api_key="admin",
        storage_backend="postgres",
        database_url="postgresql://test:test@localhost:5432/db",
    )
    # This should not raise any exceptions
    validate_production_credentials(settings)


def test_validator_fails_on_empty_keys_in_production():
    """Verify that validator raises ValueError in production if any key is empty."""
    settings = MockSettings(
        env="production",
        api_key="",
        operator_api_key="operator_key_strong_123",
        admin_api_key="admin_key_strong_123",
    )
    with pytest.raises(ValueError, match="is empty or not configured"):
        validate_production_credentials(settings)


def test_validator_fails_on_placeholder_keys_in_production():
    """Verify that validator raises ValueError in production if any key is a default placeholder."""
    settings = MockSettings(
        env="production",
        api_key="strong_api_key_here_123",
        operator_api_key="change-me-operator-key",
        admin_api_key="admin_key_strong_123",
    )
    with pytest.raises(ValueError, match="is set to a weak/placeholder value"):
        validate_production_credentials(settings)


def test_validator_fails_on_generated_placeholder_keys_in_production():
    """Generated example placeholders should fail even when they are long."""
    settings = MockSettings(
        env="production",
        api_key="CHANGE_ME_GENERATE_STRONG_API_KEY",
        operator_api_key="strong_key_operator_12345",
        admin_api_key="strong_key_admin_12345",
    )
    with pytest.raises(ValueError, match="is set to a weak/placeholder value"):
        validate_production_credentials(settings)


def test_validator_fails_on_duplicate_role_keys_in_production():
    """User, operator, and admin API keys must remain separate in production."""
    settings = MockSettings(
        env="production",
        api_key="same_strong_key_value_12345",
        operator_api_key="same_strong_key_value_12345",
        admin_api_key="admin_key_strong_12345",
    )
    with pytest.raises(ValueError, match="must be distinct"):
        validate_production_credentials(settings)


def test_validator_fails_on_short_keys_in_production():
    """Verify that validator raises ValueError in production if any key is less than 16 characters."""
    settings = MockSettings(
        env="production",
        api_key="strong_key_123",
        operator_api_key="too_short",
        admin_api_key="admin_key_strong_123",
    )
    with pytest.raises(ValueError, match="is too short"):
        validate_production_credentials(settings)


def test_validator_fails_on_missing_db_url_in_postgres_production():
    """Verify that validator raises ValueError in production with postgres backend if DATABASE_URL is missing."""
    settings = MockSettings(
        env="production",
        api_key="strong_key_api_12345",
        operator_api_key="strong_key_operator_12345",
        admin_api_key="strong_key_admin_12345",
        storage_backend="postgres",
        database_url="",
    )
    # Ensure raw env is also empty
    if "DATAFORGE_DATABASE_URL" in os.environ:
        del os.environ["DATAFORGE_DATABASE_URL"]

    with pytest.raises(ValueError, match="DATAFORGE_DATABASE_URL is not configured"):
        validate_production_credentials(settings)


def test_validator_fails_on_weak_db_password_in_postgres_production():
    """Verify that validator raises ValueError in production with postgres backend if database password is weak/default."""
    settings = MockSettings(
        env="production",
        api_key="strong_key_api_12345",
        operator_api_key="strong_key_operator_12345",
        admin_api_key="strong_key_admin_12345",
        storage_backend="postgres",
        database_url="postgresql://postgres:change-me@localhost:5432/db",
    )
    with pytest.raises(ValueError, match="password is set to a weak/placeholder value"):
        validate_production_credentials(settings)


def test_validator_fails_on_generated_placeholder_db_password_in_production(monkeypatch):
    """Postgres URL password validation should reject generated placeholder text."""
    monkeypatch.delenv("DATAFORGE_DATABASE_URL", raising=False)
    settings = MockSettings(
        env="production",
        api_key="strong_key_api_12345",
        operator_api_key="strong_key_operator_12345",
        admin_api_key="strong_key_admin_12345",
        storage_backend="postgres",
        database_url=(
            "postgresql://postgres:CHANGE_ME_GENERATE_STRONG_DB_PASSWORD@localhost:5432/db"
        ),
    )
    with pytest.raises(ValueError, match="password is set to a weak/placeholder value"):
        validate_production_credentials(settings)


def test_validator_fails_on_short_db_password_in_postgres_production():
    """Verify that validator raises ValueError in production with postgres backend if database password is too short."""
    settings = MockSettings(
        env="production",
        api_key="strong_key_api_12345",
        operator_api_key="strong_key_operator_12345",
        admin_api_key="strong_key_admin_12345",
        storage_backend="postgres",
        database_url="postgresql://postgres:short@localhost:5432/db",
    )
    with pytest.raises(ValueError, match="password is too short"):
        validate_production_credentials(settings)


def test_validator_passes_on_strong_credentials_in_production():
    """Verify that validator succeeds with zero exceptions under a strong credential setup."""
    settings = MockSettings(
        env="production",
        api_key="strong_key_api_12345",
        operator_api_key="strong_key_operator_12345",
        admin_api_key="strong_key_admin_12345",
        storage_backend="postgres",
        database_url="postgresql://postgres:strong_db_password_12345@localhost:5432/db",
    )
    # This should pass without raising ValueError
    validate_production_credentials(settings)
