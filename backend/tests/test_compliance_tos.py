"""Comp 4: ToS violation detection — test ToS violation flagging."""

from __future__ import annotations

from typing import Any

KNOWN_RESTRICTIVE_DOMAINS: dict[str, str] = {
    "facebook.com": "Prohibits automated data collection",
    "linkedin.com": "Scraping restricted by User Agreement",
    "amazon.com": "Prohibits automated access",
    "twitter.com": "Automated scraping prohibited",
    "instagram.com": "Prohibits scraping without permission",
    "pinterest.com": "Prohibits automated collection",
    "indeed.com": "Scraping restrictions apply",
}


def _check_tos_compliance(url: str) -> dict[str, Any]:
    """Check if a URL's domain has known ToS restrictions on scraping."""
    from urllib.parse import urlparse

    domain = urlparse(url).netloc.lower()

    for restrictive_domain, reason in KNOWN_RESTRICTIVE_DOMAINS.items():
        if domain == restrictive_domain or domain.endswith("." + restrictive_domain):
            return {
                "compliant": False,
                "domain": domain,
                "reason": f"Known ToS restriction: {reason}",
                "requires_acknowledgment": True,
            }
    return {"compliant": True, "domain": domain, "reason": None, "requires_acknowledgment": False}


class TestToSDetection:
    def test_known_restrictive_domain_flagged(self) -> None:
        for domain in ["facebook.com", "linkedin.com", "amazon.com"]:
            result = _check_tos_compliance(f"https://{domain}/page")
            assert result["compliant"] is False
            assert result["requires_acknowledgment"] is True

    def test_subdomain_of_restrictive_domain(self) -> None:
        result = _check_tos_compliance("https://careers.linkedin.com/jobs")
        assert result["compliant"] is False

    def test_unknown_domain_compliant(self) -> None:
        result = _check_tos_compliance("https://example.com/page")
        assert result["compliant"] is True
        assert result["requires_acknowledgment"] is False

    def test_open_data_domain_compliant(self) -> None:
        for domain in ["books.toscrape.com", "quotes.toscrape.com", "httpbin.org"]:
            result = _check_tos_compliance(f"https://{domain}")
            assert result["compliant"] is True


class TestToSAcknowledgment:
    def test_acknowledgment_required_for_restricted(self) -> None:
        result = _check_tos_compliance("https://twitter.com/user")
        assert result["requires_acknowledgment"] is True

    def test_no_acknowledgment_for_clean(self) -> None:
        result = _check_tos_compliance("https://example.org")
        assert result["requires_acknowledgment"] is False

    def test_reason_provided_for_flag(self) -> None:
        result = _check_tos_compliance("https://amazon.com/product")
        assert "restriction" in result["reason"].lower()
