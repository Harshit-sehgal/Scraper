"""Comp 3: Robots.txt sitemap discovery — test sitemap discovery from robots.txt."""
from __future__ import annotations

import re
from typing import Any

SITEMAP_DIRECTIVE_RE = re.compile(r"^sitemap:\s*(\S+)", re.IGNORECASE)


def _parse_sitemaps_from_robots(robots_txt: str) -> list[str]:
    """Extract sitemap URLs from a robots.txt body."""
    sitemaps = []
    for line in robots_txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = SITEMAP_DIRECTIVE_RE.match(line)
        if match:
            sitemaps.append(match.group(1))
    return sitemaps


def _discover_sitemaps(robots_txt: str | None) -> dict[str, Any]:
    """Discover sitemaps from robots.txt content.
    
    Returns structured result with sitemap URLs.
    """
    if not robots_txt:
        return {"sitemaps": [], "count": 0, "error": None}
    sitemaps = _parse_sitemaps_from_robots(robots_txt)
    return {
        "sitemaps": sitemaps,
        "count": len(sitemaps),
        "error": None,
    }


class TestSitemapParsing:
    def test_single_sitemap(self) -> None:
        robots = "User-agent: *\nDisallow: /private/\nSitemap: https://example.com/sitemap.xml\n"
        sitemaps = _parse_sitemaps_from_robots(robots)
        assert sitemaps == ["https://example.com/sitemap.xml"]

    def test_multiple_sitemaps(self) -> None:
        robots = (
            "Sitemap: https://example.com/sitemap.xml\n"
            "Sitemap: https://example.com/sitemap2.xml\n"
            "Sitemap: https://example.com/news-sitemap.xml\n"
        )
        sitemaps = _parse_sitemaps_from_robots(robots)
        assert len(sitemaps) == 3

    def test_no_sitemap_directive(self) -> None:
        robots = "User-agent: *\nDisallow: /\n"
        sitemaps = _parse_sitemaps_from_robots(robots)
        assert sitemaps == []

    def test_empty_robots(self) -> None:
        assert _parse_sitemaps_from_robots("") == []

    def test_sitemap_with_comments(self) -> None:
        robots = (
            "# robots.txt for example.com\n"
            "Sitemap: https://example.com/sitemap.xml\n"
            "# End of file\n"
        )
        sitemaps = _parse_sitemaps_from_robots(robots)
        assert sitemaps == ["https://example.com/sitemap.xml"]

    def test_case_insensitive_directive(self) -> None:
        robots = "SITEMAP: https://example.com/sitemap.xml\nsitemap: https://example.com/other.xml\n"
        sitemaps = _parse_sitemaps_from_robots(robots)
        assert len(sitemaps) == 2


class TestSitemapDiscovery:
    def test_discover_from_robots(self) -> None:
        result = _discover_sitemaps("User-agent: *\nSitemap: https://example.com/sitemap.xml\n")
        assert result["count"] == 1
        assert "https://example.com/sitemap.xml" in result["sitemaps"]

    def test_discover_empty_robots(self) -> None:
        result = _discover_sitemaps("")
        assert result["count"] == 0

    def test_discover_none_robots(self) -> None:
        result = _discover_sitemaps(None)
        assert result["count"] == 0

    def test_discover_no_sitemaps(self) -> None:
        result = _discover_sitemaps("User-agent: *\nDisallow: /api/\n")
        assert result["count"] == 0
