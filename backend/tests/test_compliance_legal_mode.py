"""Comp 5: Legal-only extraction mode — test legal mode disabling bypass features."""
from __future__ import annotations

from typing import Any


class LegalModeConfig:
    """Configuration for legal-only extraction mode.
    
    In legal mode, all bypass features are disabled:
    - No proxy rotation
    - No stealth/anti-bot evasion
    - No CAPTCHA solving
    - robots.txt must be respected
    - crawl-delay must be enforced
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.proxy_rotation = not enabled
        self.stealth_evasion = not enabled
        self.captcha_solving = not enabled
        self.robots_enforcement = enabled
        self.crawl_delay_enforcement = enabled
        self.tos_check_required = enabled

    def to_dict(self) -> dict[str, Any]:
        return {
            "legal_mode": self.enabled,
            "features": {
                "proxy_rotation": self.proxy_rotation,
                "stealth_evasion": self.stealth_evasion,
                "captcha_solving": self.captcha_solving,
                "robots_enforcement": self.robots_enforcement,
                "crawl_delay_enforcement": self.crawl_delay_enforcement,
                "tos_check_required": self.tos_check_required,
            },
        }


class TestLegalModeDefaults:
    def test_legal_mode_disabled_by_default(self) -> None:
        config = LegalModeConfig()
        assert config.enabled is False

    def test_bypass_features_enabled_by_default(self) -> None:
        config = LegalModeConfig()
        assert config.proxy_rotation is True
        assert config.stealth_evasion is True
        assert config.captcha_solving is True

    def test_robots_not_forced_by_default(self) -> None:
        config = LegalModeConfig()
        assert config.robots_enforcement is False


class TestLegalModeEnabled:
    def test_legal_mode_disables_proxy_rotation(self) -> None:
        config = LegalModeConfig(enabled=True)
        assert config.proxy_rotation is False

    def test_legal_mode_disables_stealth(self) -> None:
        config = LegalModeConfig(enabled=True)
        assert config.stealth_evasion is False

    def test_legal_mode_disables_captcha_solving(self) -> None:
        config = LegalModeConfig(enabled=True)
        assert config.captcha_solving is False

    def test_legal_mode_enforces_robots(self) -> None:
        config = LegalModeConfig(enabled=True)
        assert config.robots_enforcement is True

    def test_legal_mode_enforces_crawl_delay(self) -> None:
        config = LegalModeConfig(enabled=True)
        assert config.crawl_delay_enforcement is True

    def test_legal_mode_requires_tos_check(self) -> None:
        config = LegalModeConfig(enabled=True)
        assert config.tos_check_required is True


class TestLegalModeSerialization:
    def test_to_dict_includes_mode(self) -> None:
        config = LegalModeConfig(enabled=True)
        d = config.to_dict()
        assert d["legal_mode"] is True

    def test_to_dict_includes_features(self) -> None:
        config = LegalModeConfig(enabled=False)
        d = config.to_dict()
        assert "features" in d
        assert d["features"]["proxy_rotation"] is True
        assert d["features"]["robots_enforcement"] is False
