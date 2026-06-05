"""Tests for the ``RATE_LIMIT_DB_BACKED`` auto-promotion in ``Settings``.

A multi-process deployment cannot share an in-process rate-limit
counter across workers, so production-like environments should
default the flag to True. Operators can opt out by setting the env
var (or the init kwarg) explicitly to False.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def clean_rate_limit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAFORGE_RATE_LIMIT_DB_BACKED", raising=False)
    monkeypatch.delenv("DATAFORGE_ENV", raising=False)


class TestRateLimitDbBackedPromotion:
    def test_production_env_promotes_when_unset(
        self,
        clean_rate_limit_env: None,
    ) -> None:
        from app.config import Settings

        s = Settings(_env_file="/dev/null", ENV="production")
        assert s.RATE_LIMIT_DB_BACKED is True

    def test_staging_env_promotes_when_unset(
        self,
        clean_rate_limit_env: None,
    ) -> None:
        from app.config import Settings

        s = Settings(_env_file="/dev/null", ENV="staging")
        assert s.RATE_LIMIT_DB_BACKED is True

    def test_development_env_keeps_default(self, clean_rate_limit_env: None) -> None:
        from app.config import Settings

        s = Settings(_env_file="/dev/null", ENV="development")
        assert s.RATE_LIMIT_DB_BACKED is False

    def test_explicit_false_is_respected_in_production(
        self,
        clean_rate_limit_env: None,
    ) -> None:
        from app.config import Settings

        s = Settings(_env_file="/dev/null", ENV="production", RATE_LIMIT_DB_BACKED=False)
        assert s.RATE_LIMIT_DB_BACKED is False

    def test_explicit_true_is_respected_in_development(
        self,
        clean_rate_limit_env: None,
    ) -> None:
        from app.config import Settings

        s = Settings(_env_file="/dev/null", ENV="development", RATE_LIMIT_DB_BACKED=True)
        assert s.RATE_LIMIT_DB_BACKED is True

    def test_env_var_explicit_false_is_respected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.config import Settings

        monkeypatch.setenv("DATAFORGE_ENV", "production")
        monkeypatch.setenv("DATAFORGE_RATE_LIMIT_DB_BACKED", "false")
        s = Settings(_env_file="/dev/null")
        assert s.RATE_LIMIT_DB_BACKED is False
