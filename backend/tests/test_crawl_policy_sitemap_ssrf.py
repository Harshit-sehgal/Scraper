"""Tests for the SSRF defense in crawl_policy.discover_sitemaps.

A security audit found that ``discover_sitemaps`` returned sitemap
URLs extracted from a remote ``robots.txt`` without validating them. A
downstream consumer of the API that fetched the returned URLs without
re-validating would have been exposed to DNS-rebinding / private-IP
pivot — e.g. if ``example.com`` later resolved to ``127.0.0.1`` and
the operator reran discovery.

The fix adds ``_looks_like_valid_sitemap_url`` which rejects:

  - URLs without an http(s):// scheme prefix
  - URLs whose hostname is RFC1918 / loopback / link-local / CGNAT /
    cloud metadata / IPv6-loopback / IPv6-link-local / internal DNS
  - rejected URLs are dropped from the returned list (and a debug
    log line records why)

Plus the standard fallback URL is constructed only after the
caller-supplied domain already survived ``validate_public_http_url``
on the ``robots_url`` — so the final URL is safe by construction.

These tests verify the helper directly (unit-style, no network).
The integration tests for ``discover_sitemaps`` itself live in
test_crawl_policy_sitemap.py and exercise the live HTTP path.
"""

from __future__ import annotations

import pytest
from app.crawl_policy import _looks_like_valid_sitemap_url

# Hosts that the SSRF defense MUST reject. Mirrors the targets used in
# test_notification_channel_ssrf.py so the new defense has the same
# coverage as the rest of the SSRF chain.
SSRF_REJECTIONS = [
    "http://169.254.169.254/sitemap.xml",  # AWS IMDS
    "http://localhost:6379/sitemap.xml",
    "http://127.0.0.1:9000/sitemap.xml",
    "http://10.0.0.5/sitemap.xml",  # RFC1918
    "http://172.16.5.5/sitemap.xml",  # RFC1918
    "http://192.168.1.1/sitemap.xml",  # RFC1918
    "http://100.64.0.1/sitemap.xml",  # CGNAT
    "http://[::1]/sitemap.xml",  # IPv6 loopback
    "http://[fe80::1]/sitemap.xml",  # IPv6 link-local
    "http://metadata.google.internal/sitemap.xml",
    "http://internal.svc.cluster.local/sitemap.xml",
    # Disallowed schemes (sitemaps MUST be http(s))
    "gopher://example.com/sitemap.xml",
    "ftp://example.com/sitemap.xml",
    "file:///etc/sitemap.xml",
    "javascript:alert(1)",
]


class TestSitemapURLValidationRejectsSSRF:
    """Every private-IP / disallowed-scheme / internal-DNS sitemap URL
    MUST be rejected so it never reaches a downstream fetcher."""

    @pytest.mark.parametrize("url", SSRF_REJECTIONS)
    def test_rejected(self, url: str) -> None:
        assert _looks_like_valid_sitemap_url(url) is False, f"URL {url!r} should have been rejected"


class TestSitemapURLValidationAcceptsPublic:
    """Public, http(s)-scheme sitemap URLs MUST be accepted."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/sitemap.xml",
            "http://example.com/sitemap.xml",
            "https://www.example.com/sitemap-products.xml",
            "http://8.8.8.8/sitemap.xml",  # public IP literal
            "https://hooks.slack.com/sitemap.xml",
        ],
    )
    def test_accepted(self, url: str) -> None:
        assert _looks_like_valid_sitemap_url(url) is True, f"URL {url!r} should have been accepted"


class TestSitemapURLValidationEdgeInputs:
    """Empty / whitespace / scheme-only paths."""

    def test_empty_string_rejected(self) -> None:
        assert _looks_like_valid_sitemap_url("") is False

    def test_whitespace_only_rejected(self) -> None:
        assert _looks_like_valid_sitemap_url("   ") is False

    def test_scheme_only_rejected(self) -> None:
        """A URL that's just the scheme is missing a host — rejected."""
        # After .startswith(("https://", "http://")) check, the URL
        # has nothing left to validate, so validate_public_http_url
        # returns False or raises.
        assert _looks_like_valid_sitemap_url("https://") is False
