"""Tests for the centralised runtime-config helpers in ``app.globals``.

The legacy ``CONFIG`` dict used to carry its own defaults that drifted
from ``Settings``. These tests pin the new contract:

* ``rebuild_config_from_settings`` overwrites ``CONFIG`` with the values
  from ``Settings``.
* ``config_view`` returns a fresh dict, always consistent with the
  current settings instance.
* After a settings change followed by a rebuild, the legacy readers
  see the new values.
"""

from __future__ import annotations

import pytest
from app.globals import CONFIG, config_view, rebuild_config_from_settings


class TestConfigView:
    def test_config_view_returns_full_dict(self) -> None:
        view = config_view()
        for key in (
            "max_discovery_urls",
            "per_url_timeout_seconds",
            "max_job_runtime_seconds",
            "ai_structuring_timeout_seconds",
            "insight_timeout_seconds",
            "max_job_history",
            "max_recycle_bin_history",
        ):
            assert key in view, f"missing key: {key}"

    def test_config_view_is_a_fresh_dict_each_call(self) -> None:
        """Mutating the returned dict must not affect later reads."""
        a = config_view()
        a["max_discovery_urls"] = -1  # type: ignore[index]
        b = config_view()
        assert b["max_discovery_urls"] != -1

    def test_config_view_matches_settings(self) -> None:
        from app.config import settings

        view = config_view()
        assert view["max_discovery_urls"] == settings.MAX_DISCOVERY_URLS
        assert view["max_job_history"] == settings.MAX_JOB_HISTORY


class TestRebuildConfigFromSettings:
    def test_rebuild_overwrites_legacy_config(self) -> None:
        """After a rebuild, the legacy ``CONFIG`` reflects current
        ``Settings`` (not its module-level defaults).
        """
        # Mutate the legacy dict to a clearly-wrong value.
        CONFIG["max_discovery_urls"] = 999
        try:
            rebuild_config_from_settings()
            from app.config import settings

            assert CONFIG["max_discovery_urls"] == settings.MAX_DISCOVERY_URLS
        finally:
            # Always restore for downstream tests.
            rebuild_config_from_settings()

    def test_rebuild_returns_the_config_dict(self) -> None:
        """The helper returns the (refreshed) module-level dict for
        ergonomic chaining.
        """
        result = rebuild_config_from_settings()
        assert result is CONFIG

    def test_rebuild_keeps_keys_in_sync_after_settings_change(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If settings change at runtime (e.g. via env reload), a rebuild
        propagates the change to legacy readers.
        """
        from app.config import settings

        # Bump one limit on the live settings object.
        original = settings.MAX_JOB_HISTORY
        try:
            monkeypatch.setattr(settings, "MAX_JOB_HISTORY", 1234)
            rebuild_config_from_settings()
            assert CONFIG["max_job_history"] == 1234
        finally:
            monkeypatch.setattr(settings, "MAX_JOB_HISTORY", original)
            rebuild_config_from_settings()
